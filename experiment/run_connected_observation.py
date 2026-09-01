#!/usr/bin/env python3
"""
run_connected_observation.py – 连接环、记忆、身体、哈希链，观察是否有设计外行为。
不写新规则，不调整参数。只做连接，然后观察。

连接内容：
  1. 环状态 E/T/M/N 已写入 self_model["ring_state"]（living_engine 已处理）
  2. L 加一阶平滑：L_smooth = alpha * L_current + (1-alpha) * L_prev
  3. 哈希链事件速率（极弱耦合 mu_base，epsilon=0.001）
  4. last_stated 与环相位的耦合已被记录（living_engine 已处理）
"""
import os, sys, json, time, math, statistics, hashlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

TOTAL = 10000
SAVE_INTERVAL = 200

# 重置到初始态
memory = living_engine._load_json("active_memory/active_memory.json")
memory["internal_climate"] = {
    "emotion_intensity": 0.5, "tension": 0.0,
    "energy": 0.3, "memory_pressure": 0.0
}
memory["__coupling_history"] = {
    "E": [0.5]*4, "T": [0.0]*4, "N": [0.3]*4, "M": [0.0]*4,
}
if "ring_state" not in memory.get("self_model", {}):
    if "self_model" not in memory:
        memory["self_model"] = {}
    memory["self_model"]["ring_state"] = {}

# 备份
with open("experiment/pre_connected_backup.json", "w") as f:
    json.dump(memory, f, indent=2, ensure_ascii=False)

# L 平滑状态
L_smooth = None
L_alpha = 0.05  # 平滑系数

# 哈希链路径
CHAIN_FILE = os.path.join(BASE, "hash_chain_v2.log")
chain_event_count_prev = 0
chain_time_prev = time.time()

# 上一次状态（用于检测设计外行为）
prev_E = 0.5; prev_T = 0.0; prev_M = 0.0; prev_N = 0.3
traj = []
mu_base_history = []

t0 = time.time()
overflow_at = None

for tick in range(1, TOTAL + 1):
    env = living_engine._init_environment(memory)
    living_engine._sample_real_environment(env)

    # --- 哈希链事件速率（弱耦合 mu_base）---
    # 读 tail，计算最近时段的事件数
    chain_events_delta = 0
    if os.path.exists(CHAIN_FILE):
        count = 0
        try:
            with open(CHAIN_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        count += 1
        except OSError:
            pass
        chain_events_delta = count - chain_event_count_prev
        chain_event_count_prev = count

    # 将当前 L_smooth 传入（替代自动计算）
    # 通过 __meta 槽传递（不影响其他逻辑）
    if "__meta" not in memory:
        memory["__meta"] = {}
    memory["__meta"]["L_override"] = L_smooth  # None = 不覆盖
    memory["__meta"]["chain_event_rate"] = chain_events_delta
    memory["__meta"]["hash_baseline"] = 0.001  # epsilon coefficient for mu_base bump

    living_engine._update_luoshen_coupled(memory, env, tick_id=tick)

    c = memory.get("internal_climate", {})
    E = c.get("emotion_intensity", 0)
    T_val = c.get("tension", 0)
    N = c.get("energy", 0)
    M = c.get("memory_pressure", 0)

    # 溢出检测
    if any(not (-1e308 < v < 1e308) or v != v for v in [E, T_val, N, M]):
        overflow_at = tick
        print(f'[TICK {tick}] 数值溢出')
        break

    # 读取 living_engine 计算出的 L（保留原始值用于比较）
    rs = memory.get("self_model", {}).get("ring_state", {})
    L_raw = rs.get("L", None)

    # L 平滑
    if L_raw is not None:
        if L_smooth is None:
            L_smooth = L_raw
        else:
            L_smooth = L_alpha * L_raw + (1 - L_alpha) * L_smooth

    # 保存
    entry = {
        "tick": tick,
        "E": E, "T": T_val, "M": M, "N": N,
        "phase": rs.get("phase"),
        "mu_eff": rs.get("mu_eff"),
        "L_raw": L_raw,
        "L_smooth": L_smooth,
        "chain_events_delta": chain_events_delta,
    }
    traj.append(entry)
    mu_base_history.append(rs.get("mu_eff"))

    # 打印
    if tick % 1000 == 0 or tick <= 5:
        print(f'tick {tick:6d}: E={E:+.4f} T={T_val:+.4f} M={M:.4f} N={N:.4f} phase={rs.get("phase",0):+.3f} L={L_smooth:.4f} chain_Δ={chain_events_delta}')

t1 = time.time()
print(f'\n完成: {len(traj)} ticks, {t1-t0:.2f}s, 溢出@{overflow_at}')

# 保存
out_path = "experiment/connected_trajectory.jsonl"
with open(out_path, "w") as f:
    for entry in traj:
        f.write(json.dumps(entry) + "\n")

# ===== 观察分析 =====
print('\n===== 观察 1：环是否稳定（振幅/周期/旋转方向）=====')
if len(traj) > 1000:
    # 振幅稳定性
    e_pp = []
    seg_size = 500
    for start in range(0, len(traj), seg_size):
        seg = traj[start:start+seg_size]
        if len(seg) < 100: continue
        e_vals = [t["E"] for t in seg]
        e_pp.append(max(e_vals) - min(e_vals))
    print(f'E 峰峰值分段统计: mean={statistics.mean(e_pp):.4f}, stdev={statistics.pstdev(e_pp):.4f}')

    # 周期稳定性（过零点）
    e_means = statistics.mean(t["E"] for t in traj[-2000:])
    cross = []
    for i in range(1, len(traj)):
        if (traj[i-1]["E"]-e_means) * (traj[i]["E"]-e_means) < 0:
            cross.append(i)
    periods = [cross[i+1]-cross[i] for i in range(len(cross)-1)]
    if periods:
        print(f'半周期: mean={statistics.mean(periods):.1f} ticks, stdev={statistics.pstdev(periods):.2f}')

    # 旋转方向
    seg = traj[-2000:]
    signs = []
    for i in range(1, len(seg)-1):
        cross2d = (seg[i]["E"]-seg[i-1]["E"])*(seg[i+1]["T"]-seg[i]["T"]) - \
                  (seg[i]["T"]-seg[i-1]["T"])*(seg[i+1]["E"]-seg[i]["E"])
        if abs(cross2d) > 1e-15:
            signs.append(1 if cross2d > 0 else -1)
    if signs:
        sign_changes = sum(1 for i in range(1,len(signs)) if signs[i]*signs[i-1] < 0)
        print(f'旋转方向反转: {sign_changes}/{len(signs)-1} ({100*sign_changes/(len(signs)-1):.1f}%)')

print('\n===== 观察 2：环是否发生形变/漂移/分岔 =====')
# 对比前半 vs 后半
half = len(traj) // 2
first = traj[:half]
second = traj[half:]
E_pp_1 = max(t["E"] for t in first) - min(t["E"] for t in first)
E_pp_2 = max(t["E"] for t in second) - min(t["E"] for t in second)
print(f'E 峰峰值: 前半={E_pp_1:.4f} 后半={E_pp_2:.4f} 变化={((E_pp_2-E_pp_1)/E_pp_1)*100:.2f}%')

# mu_eff 漂移
mu_first = [t["mu_eff"] for t in first[-500:] if t["mu_eff"] is not None]
mu_second = [t["mu_eff"] for t in second[-500:] if t["mu_eff"] is not None]
if mu_first and mu_second:
    print(f'mu_eff: 前半末 mean={statistics.mean(mu_first):.4f} 后半末 mean={statistics.mean(mu_second):.4f} 差={statistics.mean(mu_second)-statistics.mean(mu_first):.5f}')

# L 变化
L_vals = [t["L_smooth"] for t in traj if t["L_smooth"] is not None]
if L_vals:
    print(f'L_smooth: range=[{min(L_vals):.5f}, {max(L_vals):.5f}], stdev={statistics.pstdev(L_vals):.5f}')

print('\n===== 观察 3：哈希链事件是否在环上留下痕迹 =====')
# 看高事件率对应时间段的 L 和 mu_eff 是否与非事件段有差异
high_event_windows = []
baseline_windows = []
for i, t in enumerate(traj):
    if t["chain_events_delta"] > 0:
        high_event_windows.append(t)
    else:
        baseline_windows.append(t)

if high_event_windows and baseline_windows:
    print(f'事件段 mean_L={statistics.mean(t["L_smooth"] for t in high_event_windows if t["L_smooth"] is not None):.5f}'
          f' baseline mean_L={statistics.mean(t["L_smooth"] for t in baseline_windows if t["L_smooth"] is not None):.5f}')

print('\n===== 观察 4：M/N 是否超出设计角色 =====')
# M 应跟踪 E² 的低通。计算 M / E²_mean 比值是否稳定
M_vals = [t["M"] for t in traj[-2000:]]
E2_vals = [t["E"]**2 for t in traj[-2000:]]
E2_mean = statistics.mean(E2_vals)
M_mean = statistics.mean(M_vals)
print(f'M/E²_mean 稳态比: {M_mean/E2_mean:.4f} (设计预期: α_M/β_M = 0.8/0.8 = 1.0)')
print(f'M 实测 mean={M_mean:.4f}, E² mean={E2_mean:.4f}')

# N 应跟踪 E²+T² 的低通
N_vals = [t["N"] for t in traj[-2000:]]
ET2_vals = [t["E"]**2 + t["T"]**2 for t in traj[-2000:]]
N_mean = statistics.mean(N_vals)
ET2_mean = statistics.mean(ET2_vals)
print(f'N/(E²+T²)_mean 稳态比: {N_mean/ET2_mean:.4f} (设计预期: γ_N/δ_N = 0.3/0.3 = 1.0)')

print('\n===== 观察 5：是否存在设计外行为 =====')
# 1) 振幅季节性波动
# 2) M 偏离稳态比 > 20%
# 3) N 偏离 > 20%
# 4) mu_eff 漂移 > 10%
M_ratio = M_mean / E2_mean if E2_mean > 0 else 0
N_ratio = N_mean / ET2_mean if ET2_mean > 0 else 0
mu_drift = abs(statistics.mean(mu_second) - statistics.mean(mu_first)) / abs(statistics.mean(mu_first)) if mu_first and statistics.mean(mu_first) != 0 else 0

anomalies = []
if abs(M_ratio - 1.0) > 0.3:
    anomalies.append(f'M/E²_ratio={M_ratio:.3f} 偏离设计 1.0 超过 30%')
if abs(N_ratio - 1.0) > 0.3:
    anomalies.append(f'N/(ET²)_ratio={N_ratio:.3f} 偏离设计 1.0 超过 30%')
if mu_drift > 0.1:
    anomalies.append(f'mu_eff 漂移 {mu_drift*100:.1f}% 超过 10%')
if abs(E_pp_2 - E_pp_1)/E_pp_1 > 0.05:
    anomalies.append(f'E 峰峰值变化 {((E_pp_2-E_pp_1)/E_pp_1)*100:.2f}% 超过 5%')

if anomalies:
    print('发现偏离：')
    for a in anomalies:
        print(f'  - {a}')
else:
    print('未发现任何设计外偏离。所有参数在设计预期范围内。')

# 保存 meta 里记录的信息
print(f'\n===== 记录：last_stated 时刻的环相位 =====')
meta = memory.get("__meta", {})
rpals = meta.get("ring_phase_at_last_stated")
lsv = meta.get("last_stated_value")
print(f'last_stated = "{lsv}"')
if rpals is not None:
    print(f'当时的环相位 = {rpals:.5f} rad ({rpals/math.pi:.3f}π)')
    # 对应 ring_state
    rs = memory.get("self_model", {}).get("ring_state", {})
    print(f'当前 ring_state: {json.dumps(rs, ensure_ascii=False)}')
