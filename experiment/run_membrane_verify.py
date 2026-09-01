#!/usr/bin/env python3
"""
膜 S 小规模验证：10000 tick
观察重点：
1. S 是否从 0 开始缓慢上升并平衡（积累）
2. 环是否保持稳定
3. M/N 是否仍被动
4. 是否有设计外行为
"""
import os, sys, json, time, math, statistics

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

TOTAL = 10000
SAVE_EVERY = 10

# 加载真实 memory
memory = living_engine._load_json("active_memory/active_memory.json")
memory["internal_climate"] = {
    "emotion_intensity": 0.5, "tension": 0.0,
    "energy": 0.5, "memory_pressure": 0.0,
}
memory["__coupling_history"] = {
    "E": [0.5]*4, "T": [0.0]*4, "N": [0.5]*4, "M": [0.0]*4,
}
# 确保 ring_state 被清空用于记录
if "self_model" not in memory:
    memory["self_model"] = {}
if "ring_state" not in memory["self_model"]:
    memory["self_model"]["ring_state"] = {}

traj = []
t0 = time.time()

for tick_id in range(1, TOTAL + 1):
    env = living_engine._init_environment(memory)
    living_engine._sample_real_environment(env)
    meta = memory.get("__meta", {})
    meta["chain_event_rate"] = 0
    meta["hash_baseline"] = 0.0
    memory["__meta"] = meta

    living_engine._update_luoshen_coupled(memory, env, tick_id=tick_id)

    if tick_id % SAVE_EVERY == 0:
        c = memory["internal_climate"]
        rs = memory.get("self_model", {}).get("ring_state", {})
        traj.append({
            "tick": tick_id,
            "t": round(time.time() - t0, 4),
            "E": c["emotion_intensity"],
            "T": c["tension"],
            "N": c["energy"],
            "M": c["memory_pressure"],
            "phase": rs.get("phase"),
            "mu_eff": rs.get("mu_eff"),
            "L": rs.get("L"),
            "S": rs.get("S"),
            "S_drive": rs.get("S_drive"),
        })

t1 = time.time()
print(f"[MEMBRANE-VERIFY] done: {TOTAL} ticks in {t1-t0:.2f}s")

# 保存
with open("experiment/membrane_trajectory.jsonl", "w") as f:
    for e in traj:
        f.write(json.dumps(e) + "\n")
print(f"Trajectory saved: {len(traj)} samples")

# 分析
E_pp_full = max(e["E"] for e in traj) - min(e["E"] for e in traj)
print(f"\n=== 全局 ===")
print(f"E_pp full: {E_pp_full:.4f}")
S_init = traj[0]["S"] if traj[0]["S"] is not None else 0
S_final = traj[-1]["S"] if traj[-1]["S"] is not None else 0
print(f"S initial: {S_init:.6f}  →  S final: {S_final:.6f}")
print(f"S delta: {S_final - S_init:+.6f}")
L_mean = statistics.mean(e["L"] for e in traj if e["L"] is not None)
print(f"L mean: {L_mean:.5f}")

# S 轨迹统计
S_vals = [e["S"] for e in traj if e["S"] is not None]
S_drive_vals = [e["S_drive"] for e in traj if e["S_drive"] is not None]
print(f"S range: [{min(S_vals):.4f}, {max(S_vals):.4f}]")
print(f"S_drive range: [{min(S_drive_vals):.4f}, {max(S_drive_vals):.4f}]")

# 分前后半段
mid = len(traj) // 2
S_first_half = [e["S"] for e in traj[:mid] if e["S"] is not None]
S_second_half = [e["S"] for e in traj[mid:] if e["S"] is not None]
print(f"\n=== 积累检验 ===")
print(f"S 前半段: mean={statistics.mean(S_first_half):.4f}")
print(f"S 后半段: mean={statistics.mean(S_second_half):.4f}")
print(f"S 前后变化: {statistics.mean(S_second_half)-statistics.mean(S_first_half):+.4f}")

# 更细：每 1000 tick 一个窗口
print(f"\n=== S 时间序列（每 1000 tick 平均）===")
window = len(traj) // 10
for i in range(10):
    seg = traj[i*window:(i+1)*window]
    if not seg: continue
    s_vals = [e["S"] for e in seg if e["S"] is not None]
    e_vals = [e["E"] for e in seg]
    l_vals = [e["L"] for e in seg if e["L"] is not None]
    if s_vals:
        print(f"tick [{seg[0]['tick']:5d}-{seg[-1]['tick']:5d}]  S={statistics.mean(s_vals):+.6f} ±{statistics.pstdev(s_vals):.4f}  "
              f"E_pp={max(e_vals)-min(e_vals):.4f}  L_mean={statistics.mean(l_vals):.5f}" if l_vals else "")

# 恒常性
print(f"\n=== M/E², N/(E²+T²) ===")
mean_m = statistics.mean(e["M"] for e in traj)
mean_e2 = statistics.mean(e["E"]**2 for e in traj)
mean_n = statistics.mean(e["N"] for e in traj)
mean_e2t2 = statistics.mean(e["E"]**2 + e["T"]**2 for e in traj)
print(f"M/E²={mean_m/mean_e2:.6f}   N/(E²+T²)={mean_n/mean_e2t2:.6f}")

# E_pp 稳定性
print(f"\n=== E_pp（每 1000 tick）===")
for i in range(10):
    seg = traj[i*window:(i+1)*window]
    e_vals = [e["E"] for e in seg]
    print(f"  [{seg[0]['tick']:5d}-{seg[-1]['tick']:5d}]  E_pp={max(e_vals)-min(e_vals):.4f}")

# 相位单调
phases = [e["phase"] for e in traj if e["phase"] is not None]
phase_diffs = [phases[i+1]-phases[i] for i in range(len(phases)-1)]
for i in range(len(phase_diffs)):
    if phase_diffs[i] > math.pi: phase_diffs[i] -= 2*math.pi
    elif phase_diffs[i] < -math.pi: phase_diffs[i] += 2*math.pi
sc = sum(1 for i in range(1, len(phase_diffs)) if phase_diffs[i]*phase_diffs[i-1] < 0)
print(f"\nPhase sign_changes: {sc}/{len(phase_diffs)}")

# mu_eff 稳定性（S 影响后的 mu）
mu_vals = [e["mu_eff"] for e in traj if e["mu_eff"] is not None]
print(f"\nmu_eff range: [{min(mu_vals):.4f}, {max(mu_vals):.4f}]")
print(f"mu_eff mean: {statistics.mean(mu_vals):.4f}  stdev: {statistics.pstdev(mu_vals):.4f}")

print(f"\n[DONE]")
