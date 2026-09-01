#!/usr/bin/env python3
"""
带真实 CPU 冲击的 van der Pol 环实验。
外部 bash 控制冲击时序。本脚本只连续运行环并落盘。

时间窗对应（由外部协调）:
  Phase 1 (0-3s):      基线
  Phase 2 (3-8s):      CPU 4核满载
  Phase 3 (8-13s):     冲击后恢复
"""
import os, sys, json, time, math

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

DURATION_SEC = 14.0
SAVE_EVERY = 5            # 每 5 tick 保存一次（环 tick ~0.16ms，5 tick ≈ 0.8ms 间隔）

# 重置
memory = living_engine._load_json("active_memory/active_memory.json")
memory["internal_climate"] = {
    "emotion_intensity": 0.5, "tension": 0.0,
    "energy": 0.3, "memory_pressure": 0.0
}
memory["__coupling_history"] = {
    "E": [0.5]*4, "T": [0.0]*4, "N": [0.3]*4, "M": [0.0]*4,
}
if "self_model" not in memory:
    memory["self_model"] = {}
memory["self_model"]["ring_state"] = {}

L_smooth = None
L_alpha = 0.05

traj = []
t_start = time.time()

print(f"[RING-SHOCK] start={t_start:.3f}, duration={DURATION_SEC}s")

tick = 0
while True:
    elapsed = time.time() - t_start
    if elapsed > DURATION_SEC:
        break

    env = living_engine._init_environment(memory)
    living_engine._sample_real_environment(env)

    if "__meta" not in memory:
        memory["__meta"] = {}
    # 不覆盖 L：让 _compute_body_influence 直接读真实 sensor
    memory["__meta"]["chain_event_rate"] = 0
    memory["__meta"]["hash_baseline"] = 0.0

    living_engine._update_luoshen_coupled(memory, env, tick_id=tick + 1)

    c = memory.get("internal_climate", {})
    E = c.get("emotion_intensity", 0)
    T_val = c.get("tension", 0)
    N = c.get("energy", 0)
    M = c.get("memory_pressure", 0)

    if any(not (-1e308 < v < 1e308) or v != v for v in [E, T_val, N, M]):
        print(f"[TICK {tick+1}] 数值溢出 @ t={elapsed:.3f}s")
        break

    rs = memory.get("self_model", {}).get("ring_state", {})
    L_raw = rs.get("L", None)
    if L_raw is not None:
        if L_smooth is None:
            L_smooth = L_raw
        else:
            L_smooth = L_alpha * L_raw + (1 - L_alpha) * L_raw

    l_eff = rs.get("L", L_smooth)
    if tick % SAVE_EVERY == 0:
        traj.append({
            "tick": tick + 1,
            "t": round(elapsed, 4),
            "E": E, "T": T_val, "M": M, "N": N,
            "phase": rs.get("phase"),
            "mu_eff": rs.get("mu_eff"),
            "L": l_eff,
            "L_raw": L_raw,
        })

    tick += 1

t_end = time.time()
wall_duration = t_end - t_start
print(f"[RING-SHOCK] done: {tick} ticks, {wall_duration:.2f}s, {tick/wall_duration:.0f} ticks/s")

# 保存轨迹
with open("experiment/ring_shock_trajectory.jsonl", "w") as f:
    for entry in traj:
        f.write(json.dumps(entry) + "\n")

print(f"[RING-SHOCK] saved {len(traj)} samples to experiment/ring_shock_trajectory.jsonl")

# 时间窗分析
WINDOWS = {
    "baseline":  (0.0, 2.5),
    "pre_shock": (2.5, 3.0),
    "stress":    (3.0, 8.0),
    "post_1":    (8.0, 9.0),
    "post_2":    (9.0, 11.0),
    "post_3":    (11.0, 14.0),
}

def in_window(e, w):
    return WINDOWS[w][0] <= e["t"] < WINDOWS[w][1]

print("\n===== 时间窗分析 =====")
for wname, (t0, t1) in WINDOWS.items():
    seg = [e for e in traj if t0 <= e["t"] < t1]
    if not seg:
        print(f"  [{wname:10s}] ({t0:.1f}-{t1:.1f}s): NO DATA")
        continue
    import statistics
    E_vals = [e["E"] for e in seg]
    T_vals = [e["T"] for e in seg]
    L_vals = [e["L"] for e in seg if e["L"] is not None]
    M_vals = [e["M"] for e in seg]
    N_vals = [e["N"] for e in seg]
    e_pp = max(E_vals) - min(E_vals)
    t_pp = max(T_vals) - min(T_vals)
    e_mean = statistics.mean(E_vals)
    e_rms = math.sqrt(sum(e*e for e in E_vals)/len(E_vals))

    print(f"  [{wname:10s}] ({t0:.1f}-{t1:.1f}s): n={len(seg):5d} | "
          f"E_pp={e_pp:.4f} E_rms={e_rms:.4f} E_mean={e_mean:+.4f} | "
          f"T_pp={t_pp:.4f} | "
          f"M=[{min(M_vals):.3f},{max(M_vals):.3f}] N=[{min(N_vals):.3f},{max(N_vals):.3f}] | "
          f"L_mean={statistics.mean(L_vals):.5f}" if L_vals else f"L=N/A")

# 冲击特征提取（stress 窗口 vs baseline）
print("\n===== 冲击特征 =====")
baseline = [e for e in traj if 0.5 <= e["t"] < 2.5]
stress   = [e for e in traj if 4.0 <= e["t"] < 7.0]
post     = [e for e in traj if 9.0 <= e["t"] <= 13.0]

if baseline and stress:
    def stats_block(seg, label):
        if not seg: return
        E_vals = [e["E"] for e in seg]
        L_vals = [e["L"] for e in seg if e["L"] is not None]
        import statistics
        print(f"  [{label}]")
        print(f"    E statistics: mean={statistics.mean(E_vals):+.6f}, stdev={statistics.pstdev(E_vals):.6f}, pp={max(E_vals)-min(E_vals):.6f}")
        print(f"    T statistics: mean={statistics.mean(e['T'] for e in seg):+.6f}, stdev={statistics.pstdev(e['T'] for e in seg):.6f}")
        print(f"    M statistics: mean={statistics.mean(e['M'] for e in seg):.6f}, stdev={statistics.pstdev(e['M'] for e in seg):.6f}")
        print(f"    N statistics: mean={statistics.mean(e['N'] for e in seg):.6f}, stdev={statistics.pstdev(e['N'] for e in seg):.6f}")
        if L_vals:
            print(f"    L statistics: mean={statistics.mean(L_vals):.6f}, stdev={statistics.pstdev(L_vals):.6f}")
        # L 与 E 的相关系数
        if L_vals and len(L_vals) > 10:
            paired = [(e["E"], e["L"]) for e in seg if e["L"] is not None]
            if len(paired) > 10:
                Ev = [p[0] for p in paired]
                Lv = [p[1] for p in paired]
                em = statistics.mean(Ev); lm = statistics.mean(Lv)
                cov = sum((e-em)*(l-lm) for e,l in paired)/len(paired)
                es = statistics.pstdev(Ev); ls = statistics.pstdev(Lv)
                corr = cov/(es*ls) if es*ls > 0 else 0
                print(f"    E-L correlation: {corr:.4f}")

    stats_block(baseline, "BASELINE")
    stats_block(stress,   "STRESS")
    stats_block(post,     "POST-STRESS")

# 相位连续性分析：冲击后环是否接上了原节奏
print("\n===== 相位连续性 =====")
# 用 E 过零点的 tick 间隔判断周期
def zero_crossings(seg):
    if len(seg) < 2: return []
    m = statistics.mean(e["E"] for e in seg)
    return [i for i in range(1, len(seg)) if (seg[i-1]["E"]-m)*(seg[i]["E"]-m) < 0]

zc_base = zero_crossings(baseline)
if len(zc_base) > 2:
    periods = [zc_base[i+1]-zc_base[i] for i in range(len(zc_base)-1)]
    print(f"  baseline zero-crossings: {len(zc_base)}, mean_period={statistics.mean(periods):.1f} ticks, stdev={statistics.pstdev(periods):.2f}")

zc_post = zero_crossings(post)
if len(zc_post) > 2:
    periods = [zc_post[i+1]-zc_post[i] for i in range(len(zc_post)-1)]
    print(f"  post     zero-crossings: {len(zc_post)}, mean_period={statistics.mean(periods):.1f} ticks, stdev={statistics.pstdev(periods):.2f}")

print("\n[DONE]")
