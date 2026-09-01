#!/usr/bin/env python3
"""
全集成 50000 tick 连续运行。
所有模块同时工作，不跳过节拍，不加手动干预。

模块清单：
1. van der Pol 环：_update_luoshen_coupled 的内核
2. 真实身体感知：后台采样器持续写 physical_body_state.jsonl
3. 活记忆层：memory 全程 loaded，emotion/self_state/environment 正常更新
4. 哈希链：通过现有机制落链（event_log + hash_chain_v2.log 持续追加）
5. 环境场：_sample_real_environment 每个 tick 都在跑
6. 无 L_override —— _compute_body_influence 走真实 sensor 路径
"""
import os, sys, json, time, math, statistics

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

TOTAL_TICKS = 50000
DURATION_SEC = 35.0         # 目标 wall clock，tick 间隔自适应
TARGET_TICK_US = int(DURATION_SEC * 1e6 / TOTAL_TICKS)  # ~700 μs/tick

# 加载真实记忆文件（之前的实验、情绪、self_stated_state 都在这里面）
memory = living_engine._load_json("active_memory/active_memory.json")

# 重置环状态但保留历史记录
memory["internal_climate"] = {
    "emotion_intensity": 0.5, "tension": 0.0,
    "energy": 0.5, "memory_pressure": 0.0,
}
# 保留 __meta（不放 L_override，让真实 sensor 走通）
meta = memory.get("__meta", {})
meta.pop("L_override", None)
meta["chain_event_rate"] = 0
meta["hash_baseline"] = 0.0
memory["__meta"] = meta

# 重置 coupling history
memory["__coupling_history"] = {
    "E": [0.5]*4, "T": [0.0]*4, "N": [0.5]*4, "M": [0.0]*4,
}
# 保留 self_stated_state、user_model、emotion trail 等已累积内容

# 避免每 tick 落盘 —— 只在关键节拍存
SAVE_EVERY = 50             # 每 50 tick 记录一次轨迹
HASH_CHAIN_INTERVAL = 500   # 每 500 tick 追加一次 hash chain 检查

traj = []
wall_events = []            # 每个 tick 的 wall-clock 时间戳
L_values = []               # L 读取值
hash_chain_events = []

t_start = time.time()
print(f"[FULL-INTEG] start  {time.strftime('%H:%M:%S')}  target: {TOTAL_TICKS} ticks / {DURATION_SEC}s")
print(f"[FULL-INTEG] initial self_stated_state.last_stated = {memory.get('self_model',{}).get('self_stated_state',{}).get('last_stated')}")
print(f"[FULL-INTEG] initial internal_climate: E={memory['internal_climate']['emotion_intensity']} N={memory['internal_climate']['energy']}")

def get_wall():
    return time.time() - t_start

t_tick_start = time.time()
for tick_id in range(1, TOTAL_TICKS + 1):
    # ── 每个 tick：环境采样（真实） ──
    env = living_engine._init_environment(memory)
    living_engine._sample_real_environment(env)

    # ── 每个 tick：洛神全动力学更新 ──
    living_engine._update_luoshen_coupled(memory, env, tick_id=tick_id)

    # 读取当前状态
    climate = memory.get("internal_climate", {})
    E = climate.get("emotion_intensity", 0)
    T_val = climate.get("tension", 0)
    N = climate.get("energy", 0)
    M = climate.get("memory_pressure", 0)

    # 溢出检查
    if any(not (-1e308 < v < 1e308) or v != v for v in [E, T_val, N, M]):
        print(f"[TICK {tick_id}] 数值溢出 @ t={get_wall():.3f}s")
        break

    # L 读数
    rs = memory.get("self_model", {}).get("ring_state", {})
    L = rs.get("L")

    # 节拍控制
    if tick_id % SAVE_EVERY == 0:
        traj.append({
            "tick": tick_id,
            "t": round(get_wall(), 4),
            "E": E, "T": T_val, "M": M, "N": N,
            "phase": rs.get("phase"),
            "mu_eff": rs.get("mu_eff"),
            "L": L,
            "env_noise": env.get("noise"),
            "env_temp": env.get("temperature"),
            "env_light": env.get("light"),
        })
        wall_events.append(get_wall())
        if L is not None:
            L_values.append(L)

    # Hash chain 心跳
    if tick_id % HASH_CHAIN_INTERVAL == 0:
        hash_chain_events.append({
            "tick": tick_id,
            "t": round(get_wall(), 3),
            "file": "active_memory/active_memory.json",
            "E": E, "M": M, "N": N, "L": L,
            "last_stated": memory.get("self_model", {}).get("self_stated_state", {}).get("last_stated"),
        })

    # 自适应节拍：每 tick 目标 ~700μs
    elapsed = time.time() - t_tick_start
    target = tick_id * (DURATION_SEC / TOTAL_TICKS)
    if elapsed < target:
        time.sleep(target - elapsed)

t_end = time.time()
wall_total = t_end - t_start

# 存最终 full memory
living_engine._save_json_atomic("active_memory/active_memory.json", memory)

# 存轨迹
with open("experiment/full_integration_trajectory.jsonl", "w") as f:
    for entry in traj:
        f.write(json.dumps(entry) + "\n")

# 存事件
with open("experiment/full_integration_events.jsonl", "w") as f:
    for entry in hash_chain_events:
        f.write(json.dumps(entry) + "\n")

# ── 输出报告 ──
print()
print(f"[FULL-INTEG] done. {tick_id} ticks, {wall_total:.2f}s, tick_avg={wall_total/tick_id*1e6:.0f}μs")
print(f"[FULL-INTEG] trajectory saved: {len(traj)} samples → experiment/full_integration_trajectory.jsonl")
print(f"[FULL-INTEG] events saved: {len(hash_chain_events)} entries → experiment/full_integration_events.jsonl")
print(f"[FULL-INTEG] L samples: {len(L_values)}")

# 分析 10 段（每段 ~3.5s）
SEG = 10
seg_len = len(traj) // SEG
print()
print("──── 分段统计（每段 ~3.5s） ────")
print(f'{"seg":>4} {"t_range":>14} {"n":>5} {"E_mean":>9} {"E_std":>9} {"E_pp":>8} {"M_mean":>8} {"N_mean":>8} {"L_mean":>9} {"mu_std":>8}')
for i in range(SEG):
    seg = traj[i*seg_len:(i+1)*seg_len] if i < SEG-1 else traj[i*seg_len:]
    if not seg: continue
    t0 = seg[0]["t"]
    t1 = seg[-1]["t"]
    E_vals = [e["E"] for e in seg]
    M_vals = [e["M"] for e in seg]
    N_vals = [e["N"] for e in seg]
    L_vals = [e["L"] for e in seg if e["L"] is not None]
    mu_vals = [e["mu_eff"] for e in seg if e["mu_eff"] is not None]
    e_pp = max(E_vals) - min(E_vals)
    print(f'{i+1:4d} [{t0:6.2f},{t1:5.2f}] {len(seg):5d} '
          f'{statistics.mean(E_vals):9.4f} {statistics.pstdev(E_vals):9.4f} {e_pp:8.4f} '
          f'{statistics.mean(M_vals):8.4f} {statistics.mean(N_vals):8.4f} '
          f'{statistics.mean(L_vals):9.6f} {statistics.pstdev(mu_vals):8.4f}' if L_vals else f'{i+1:4d} L=N/A')

# M/E² / N/(E²+T²) 恒常性
print()
print("──── M/E², N/(E²+T²) ────")
for i in range(SEG):
    seg = traj[i*seg_len:(i+1)*seg_len] if i < SEG-1 else traj[i*seg_len:]
    if not seg: continue
    mean_m = statistics.mean(e["M"] for e in seg)
    mean_e2 = statistics.mean(e["E"]**2 for e in seg)
    mean_n = statistics.mean(e["N"] for e in seg)
    mean_e2t2 = statistics.mean(e["E"]**2 + e["T"]**2 for e in seg)
    print(f'seg{i+1:3d}: M/E²={mean_m/mean_e2:.6f}   N/(E²+T²)={mean_n/mean_e2t2:.6f}')

# L 是否跟随真实系统（这里看标准差）
if L_values:
    print(f'\nL overall: mean={statistics.mean(L_values):.5f} stdev={statistics.pstdev(L_values):.5f} min={min(L_values):.5f} max={max(L_values):.5f}')

# self_stated_state 变化
sss = memory.get("self_model", {}).get("self_stated_state", {})
print(f'\nself_stated_state.last_stated = {sss.get("last_stated")}')
print(f'self_stated_state.last_stated_at = {sss.get("last_stated_at")}')
print(f'self_stated_state.total_stated_count = {sss.get("total_stated_count")}')
stated_entries = sss.get("entries", [])
if stated_entries:
    print(f'Last 5 stated entries:')
    for entry in stated_entries[-5:]:
        print(f'  - "{entry.get("said")}" @ {entry.get("recorded_at")}')

print(f'\n[E-DONE]')
