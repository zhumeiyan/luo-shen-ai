#!/usr/bin/env python3
"""run_ring_experiment.py - 5000 tick 环形转换实验"""
import os, sys, json, time, math

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

import living_engine

TOTAL = 5000

# 重置到初始态
memory = living_engine._load_json("active_memory/active_memory.json")
memory["internal_climate"] = {
    "emotion_intensity": 0.5, "tension": 0.0,
    "energy": 0.3, "memory_pressure": 0.0
}
memory["__coupling_history"] = {
    "E": [0.5]*4, "T": [0.0]*4, "N": [0.3]*4, "M": [0.0]*4,
}

# 备份
with open("experiment/pre_ring_backup.json", "w") as f:
    json.dump(memory, f, indent=2, ensure_ascii=False)

traj = []
t0 = time.time()
overflow_at = None

for i in range(1, TOTAL + 1):
    env = living_engine._init_environment(memory)
    living_engine._sample_real_environment(env)
    living_engine._update_luoshen_coupled(memory, env, tick_id=i)
    c = memory.get("internal_climate", {})
    E, T_val, N, M = c.get("emotion_intensity"), c.get("tension"), c.get("energy"), c.get("memory_pressure")

    if any(not (-1e308 < v < 1e308) or v != v for v in [E, T_val, N, M]):
        overflow_at = i
        print(f'[TICK {i}] 数值溢出')
        break

    traj.append({"tick": i, "E": E, "T": T_val, "N": N, "M": M})

    if i % 500 == 0 or i <= 5:
        print(f'tick {i:5d}: E={E:10.6f}  T={T_val:10.6f}  M={M:10.6f}  N={N:10.6f}')

t1 = time.time()
print(f'\n完成: {len(traj)} ticks, {t1-t0:.2f}s, 溢出@{overflow_at}')

# 保存
with open("experiment/ring_trajectory.jsonl", "w") as f:
    for entry in traj:
        f.write(json.dumps(entry) + "\n")

# 分析
def stats(values):
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean)**2 for v in values) / n
    return mean, math.sqrt(var)

# 分段统计
seg_size = 500
segments = []
for start in range(0, len(traj), seg_size):
    seg = traj[start:start+seg_size]
    if len(seg) < 100: continue
    E_vals = [t["E"] for t in seg]
    T_vals = [t["T"] for t in seg]
    M_vals = [t["M"] for t in seg]
    N_vals = [t["N"] for t in seg]
    E_m, E_s = stats(E_vals)
    T_m, T_s = stats(T_vals)
    M_m, M_s = stats(M_vals)
    N_m, N_s = stats(N_vals)
    segments.append({
        "range": f"{seg[0]['tick']}-{seg[-1]['tick']}",
        "E": f"{E_m:.4f}±{E_s:.4f}",
        "T": f"{T_m:.4f}±{T_s:.4f}",
        "M": f"{M_m:.4f}±{M_s:.4f}",
        "N": f"{N_m:.4f}±{N_s:.4f}",
        "E_min_max": f"[{min(E_vals):.4f}, {max(E_vals):.4f}]",
        "T_min_max": f"[{min(T_vals):.4f}, {max(T_vals):.4f}]",
    })

print("\n=== 分段统计 ===")
for s in segments:
    print(f"Tick {s['range']:>12s}:  E={s['E']:>20s}  T={s['T']:>20s}  M={s['M']:>20s}  N={s['N']:>20s}")
    print(f"{'':>16s}   E∈{s['E_min_max']}  T∈{s['T_min_max']}")

# 零穿越（穿越均值）
def crossings(values):
    m = sum(values) / len(values)
    return sum(1 for i in range(1, len(values)) if (values[i-1] - m) * (values[i] - m) < 0)

last = traj[-2000:]
E_vals = [t["E"] for t in last]
T_vals = [t["T"] for t in last]
M_vals = [t["M"] for t in last]
N_vals = [t["N"] for t in last]

print(f"\n=== 环检测 (last 2000 ticks) ===")
print(f"E crossings: {crossings(E_vals)}")
print(f"T crossings: {crossings(T_vals)}")
print(f"M crossings: {crossings(M_vals)}")
print(f"N crossings: {crossings(N_vals)}")

# 幅度稳定性
E_m, E_s = stats(E_vals)
print(f"E mean={E_m:.4f} stdev={E_s:.4f}")
E_range = max(E_vals) - min(E_vals)
T_range = max(T_vals) - min(T_vals)
print(f"E peak-to-peak: {E_range:.4f}")
print(f"T peak-to-peak: {T_range:.4f}")

# 相空间旋转：相邻步叉积符号
def rotation_consistency(traj_seg):
    if len(traj_seg) < 3: return 0, 0
    signs = []
    for i in range(1, len(traj_seg) - 1):
        dE1 = traj_seg[i]["E"] - traj_seg[i-1]["E"]
        dT1 = traj_seg[i]["T"] - traj_seg[i-1]["T"]
        dE2 = traj_seg[i+1]["E"] - traj_seg[i]["E"]
        dT2 = traj_seg[i+1]["T"] - traj_seg[i]["T"]
        cross = dE1 * dT2 - dT1 * dE2
        if abs(cross) > 1e-15:
            signs.append(1 if cross > 0 else -1)
    if not signs: return 0, 0
    changes = sum(1 for i in range(1, len(signs)) if signs[i] * signs[i-1] < 0)
    return changes, len(signs)

changes, total = rotation_consistency(last)
print(f"Rotation sign changes: {changes}/{total} ({100*changes/total:.1f}%)")
if changes < total * 0.1:
    print("判定: 稳定旋转（方向一致的极限环）")
elif changes < total * 0.4:
    print("判定: 准周期旋转（有轻微摆动但总体旋转）")
else:
    print("判定: 不稳定旋转（可能收敛或混沌）")
