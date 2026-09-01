#!/usr/bin/env python3
"""
run_shock_experiment.py

实验进行中，在 t ≈ SHOCK_AT_TICK 附近,
从外部真实触发一次磁盘写（dd），观察环的响应。

这个脚本只负责跑实验。冲击事件由 run.sh 从外部注入。
实验代码里：没有"如果检测到冲击就怎样"的逻辑。
所有信号通过已存在的 L 通道自然流经 mu_base。
"""
import os, sys, json, time, math, statistics

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

TOTAL = 10000
SHOCK_AT_TICK = 5000  # 注：冲击由外部 dd 注入

# 重置到初始态
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

with open("experiment/pre_shock_backup.json", "w") as f:
    json.dump(memory, f, indent=2, ensure_ascii=False)

L_smooth = None
L_alpha = 0.05
traj = []

t_start = time.time()
overflow_at = None

for tick in range(1, TOTAL + 1):
    env = living_engine._init_environment(memory)
    living_engine._sample_real_environment(env)

    if "__meta" not in memory:
        memory["__meta"] = {}
    memory["__meta"]["L_override"] = L_smooth
    memory["__meta"]["chain_event_rate"] = 0
    memory["__meta"]["hash_baseline"] = 0.0

    living_engine._update_luoshen_coupled(memory, env, tick_id=tick)

    c = memory.get("internal_climate", {})
    E = c.get("emotion_intensity", 0)
    T_val = c.get("tension", 0)
    N = c.get("energy", 0)
    M = c.get("memory_pressure", 0)

    if any(not (-1e308 < v < 1e308) or v != v for v in [E, T_val, N, M]):
        overflow_at = tick
        print(f'[TICK {tick}] 数值溢出')
        break

    rs = memory.get("self_model", {}).get("ring_state", {})
    L_raw = rs.get("L", None)
    if L_raw is not None:
        if L_smooth is None:
            L_smooth = L_raw
        else:
            L_smooth = L_alpha * L_raw + (1 - L_alpha) * L_raw

    elapsed = time.time() - t_start

    entry = {
        "tick": tick,
        "t": round(elapsed, 4),
        "E": E, "T": T_val, "M": M, "N": N,
        "phase": rs.get("phase"),
        "mu_eff": rs.get("mu_eff"),
        "L": L_smooth,
    }
    traj.append(entry)

    if tick == SHOCK_AT_TICK:
        print(f'--- SHOCK MARK: tick={tick}, t={elapsed:.3f}s ---')
        # 记录当时的完整状态
        with open("experiment/shock_mark.json", "w") as f:
            json.dump({"tick": tick, "time": elapsed, "state": entry, "ring_state": rs}, f, indent=2)

    if tick % 1000 == 0 or tick in [SHOCK_AT_TICK - 2, SHOCK_AT_TICK, SHOCK_AT_TICK + 2]:
        print(f'tick {tick:6d} t={elapsed:.3f}s: E={E:+.4f} T={T_val:+.4f} M={M:.4f} N={N:.4f} L={L_smooth:.5f} phase={rs.get("phase",0):+.3f}')

t_end = time.time()
print(f'\n完成: {len(traj)} ticks, {t_end-t_start:.2f}s, 溢出@{overflow_at}')

# 保存轨迹
with open("experiment/shock_trajectory.jsonl", "w") as f:
    for entry in traj:
        f.write(json.dumps(entry) + "\n")

# === 冲击分析 ===
print(f'\n===== 冲击分析 (tick {SHOCK_AT_TICK}) =====')

# 找冲击点索引
shock_idx = next(i for i, e in enumerate(traj) if e["tick"] == SHOCK_AT_TICK)
traj_shock = traj[shock_idx]

# 冲击前 10 tick 的振幅 (已收敛环)
pre_window = traj[max(0, shock_idx - 10):shock_idx]
post_window = traj[shock_idx:shock_idx + 10]
recovery_window = traj[shock_idx + 100:shock_idx + 110]

def amplitude(win):
    return max(e["E"] for e in win) - min(e["E"] for e in win)

def mean_L(win):
    return statistics.mean(e["L"] for e in win)

print(f'冲击前 (tick {pre_window[0]["tick"]}-{pre_window[-1]["tick"]}): E_amplitude = {amplitude(pre_window):.4f}')
print(f'冲击时 (tick {shock_idx+1}): E={traj_shock["E"]:+.4f} T={traj_shock["T"]:+.4f} L={traj_shock["L"]:.5f}')
print(f'冲击后 (tick {post_window[0]["tick"]}-{post_window[-1]["tick"]}): E_amplitude = {amplitude(post_window):.4f}')
print(f'恢复后 (tick {recovery_window[0]["tick"]}-{recovery_window[-1]["tick"]}): E_amplitude = {amplitude(recovery_window):.4f}')

print(f'\n冲击前 mean L: {mean_L(pre_window):.5f}')
print(f'冲击时 mean L: {traj_shock["L"]:.5f}')
print(f'冲击后 mean L: {mean_L(post_window):.5f}')

# 相空间检测：冲击前后 50 tick 的 R 半径
traj_pre = traj[shock_idx - 50:shock_idx]
traj_post = traj[shock_idx:shock_idx + 50]
rad_pre = [math.sqrt(e["E"]**2 + e["T"]**2) for e in traj_pre]
rad_post = [math.sqrt(e["E"]**2 + e["T"]**2) for e in traj_post]
print(f'\n相空间半径 (sqrt(E²+T²)):')
print(f'  冲击前 50 tick 范围: [{min(rad_pre):.4f}, {max(rad_pre):.4f}]')
print(f'  冲击后 50 tick 范围: [{min(rad_post):.4f}, {max(rad_post):.4f}]')
print(f'  冲击前 mean R: {statistics.mean(rad_pre):.4f}')
print(f'  冲击后 mean R: {statistics.mean(rad_post):.4f}')

# 检测冲击是否被吸收：检查冲击后 200 tick 是否回到原环
rebound = traj[shock_idx + 200:shock_idx + 210]
if rebound:
    amp_rebound = amplitude(rebound)
    print(f'\n冲击后 200 tick 恢复段: E_amplitude = {amp_rebound:.4f}')
    if abs(amp_rebound - amplitude(pre_window)) < 0.05:
        print('判定: 冲击被吸收，环回到原振幅')
    else:
        print(f'判定: 振幅未回到原水平 (偏差 {amp_rebound - amplitude(pre_window):.4f})')

# 异常检测：相空间里是否有超过 van der Pol 环半径 3 倍标准差外的异常点
print(f'\n===== 异常检测 =====')
R_trajs = [math.sqrt(e["E"]**2 + e["T"]**2) for e in traj[-2000:]]
R_mean = statistics.mean(R_trajs)
R_std = statistics.pstdev(R_trajs)
anomalies = [(e["tick"], e["E"], e["T"], math.sqrt(e["E"]**2 + e["T"]**2))
             for e in traj[-2000:]
             if abs(math.sqrt(e["E"]**2 + e["T"]**2) - R_mean) > 3 * R_std]
print(f'相空间异常点 (>3σ from mean): {len(anomalies)} / 2000')
if anomalies:
    for a in anomalies[:10]:
        print(f'  tick {a[0]}: E={a[1]:+.4f} T={a[2]:+.4f} R={a[3]:.4f} (mean={R_mean:.4f}, σ={R_std:.4f})')

# 相位漂移：用冲击点前后各 100 tick 的平均相位差
phases_pre = [e["phase"] for e in traj_pre if e["phase"] is not None]
phases_post = [e["phase"] for e in traj_post if e["phase"] is not None]
if phases_pre and phases_post:
    # 简化：只看 E 的均值漂移（van der Pol 环持续通过零点）
    E_pre_mean = statistics.mean(e["E"] for e in traj_pre)
    E_post_mean = statistics.mean(e["E"] for e in traj_post)
    print(f'\n相位检测:')
    print(f'  冲击前 E mean: {E_pre_mean:+.6f} (环半径应 ≈ 0)')
    print(f'  冲击后 E mean: {E_post_mean:+.6f}')
    print(f'  E 均值漂移: {E_post_mean - E_pre_mean:+.6f}')
