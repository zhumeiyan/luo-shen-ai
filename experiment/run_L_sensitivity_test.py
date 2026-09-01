#!/usr/bin/env python3
"""
run_L_sensitivity_test.py

实验目标：验证 physical_body_sensor 能否捕获持续真实系统压力导致的 L 变化。
实验本身不做任何冲击。冲击由外部脚本启动（bash 后台进程）。

实验只做三件事：
  1. 连续采样真实系统状态（每_TICK_US 微秒一次）
  2. 计算 L
  3. 记录所有原始数值到 active_memory/physical_body_state.jsonl + .jsonl

不触碰环。不进行任何"如果 L 升高就怎样"的判断。
所有噪声来自真实系统。
"""
import os, sys, json, time, subprocess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import physical_body_sensor

DURATION_SEC = 20        # 总采样时长（秒）
SAMPLE_INTERVAL = 0.2     # 采样间隔（秒）— 不要太密，留给系统变化空间

print(f"[L-sensitivity] 采样 {DURATION_SEC} 次采样，每次间隔 {SAMPLE_INTERVAL}s")
print(f"[L-sensitivity] 开始时间: {time.time():.3f}")

traj = []
t_start = time.time()

i = 0
while True:
    elapsed = time.time() - t_start
    if elapsed > DURATION_SEC:
        break

    snap = physical_body_sensor.sample_body_state()
    chain_entry = physical_body_sensor.record_body_state(snap)

    # 计算各通道值用于输出
    cpu_u = snap.get("cpu_usage_ratio")
    load = snap.get("load", {}).get("load_1min") if snap.get("load") else None
    mem = snap.get("memory", {}).get("available_ratio") if snap.get("memory") else None
    rtt = snap.get("network_rtt_ms")

    # 复现 L 算法（与 _compute_body_influence 相同，方便验证）
    cpus = os.cpu_count() or 4
    L_channels = []
    L_labels = []

    if cpu_u is not None:
        c1 = min(cpu_u / 0.8, 1.0)
        L_channels.append(c1)
        L_labels.append(f"cpu={c1:.4f}")
    if load is not None:
        c2 = min(load / cpus, 1.0)
        L_channels.append(c2)
        L_labels.append(f"load={c2:.4f}")
    if mem is not None:
        c3 = max(0.0, 1.0 - mem)
        L_channels.append(c3)
        L_labels.append(f"mem={c3:.4f}")
    if rtt is not None:
        c4 = min(rtt / 100.0, 1.0)
        L_channels.append(c4)
        L_labels.append(f"rtt={c4:.4f}")

    L_val = sum(L_channels) / len(L_channels) if L_channels else None

    entry = {
        "sample": i,
        "elapsed": round(elapsed, 3),
        "t": snap["timestamp"],
        "cpu_usage_ratio": cpu_u,
        "load_1min": load,
        "mem_available_ratio": mem,
        "rtt_ms": rtt,
        "L": round(L_val, 6) if L_val is not None else None,
        "L_channels": L_labels,
    }
    traj.append(entry)

    if i % 10 == 0:
        print(f"  sample {i:4d} t={elapsed:6.2f}s L={L_val:.5f} channels=[{' '.join(L_labels)}]")

    i += 1
    time.sleep(SAMPLE_INTERVAL)

# 保存 L 时序
out_path = "experiment/L_sensitivity_timeseries.jsonl"
with open(out_path, "w") as f:
    for entry in traj:
        f.write(json.dumps(entry) + "\n")

# 输出 L 的时序统计
L_vals = [e["L"] for e in traj if e["L"] is not None]
print(f"\n[L-sensitivity] 完成: {len(traj)} 样本")

if L_vals:
    import statistics
    print(f"L 时序统计:")
    print(f"  mean = {statistics.mean(L_vals):.5f}")
    print(f"  stdev = {statistics.pstdev(L_vals):.5f}")
    print(f"  range = [{min(L_vals):.5f}, {max(L_vals):.5f}]")
    print(f"  span = {max(L_vals) - min(L_vals):.5f}")

    # 分段比较：前 1/3 vs 后 1/3
    third = len(L_vals) // 3
    early = L_vals[:third]
    late = L_vals[-third:]
    print(f"  前 1/3 mean = {statistics.mean(early):.5f}")
    print(f"  后 1/3 mean = {statistics.mean(late):.5f}")
    print(f"  漂移 = {statistics.mean(late) - statistics.mean(early):+.5f}")
