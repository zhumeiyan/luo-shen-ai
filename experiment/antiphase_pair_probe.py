#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反相锁定对探针。

两个 van der Pol 振子 A/B：
- 自然频率不同（A=1.0, B=1.05）
- 弱耦合，推动它们反相
- 不加 if-then，连续演化
- 观察相位差是否漂移
"""

import math
import csv

DT = 0.08

# 参数
MU = 0.5
OMEGA_A = 1.0
OMEGA_B = 1.05          # 5% 频差
EPS_C = 0.02            # 弱耦合
GAMMA = 0.01            # 弱阻尼（防止单向偏移）

def step(EA, TA, EB, TB, dt=DT):
    """一步积分。"""
    # A 振子（带弱耦合 + 弱阻尼）
    # 耦合: 弱拉向 -EB（反相）
    dEA = TA * dt
    dTA = (MU * (1.0 - EA*EA) * TA - OMEGA_A*OMEGA_A * EA) * dt
    dTA += -EPS_C * EB * dt          # 反相耦合
    dTA += -GAMMA * EA * dt          # 弱阻尼

    # B 振子（带弱耦合 + 弱阻尼）
    dEB = TB * dt
    dTB = (MU * (1.0 - EB*EB) * TB - OMEGA_B*OMEGA_B * EB) * dt
    dTB += -EPS_C * EA * dt          # 反相耦合
    dTB += -GAMMA * EB * dt          # 弱阻尼

    return EA + dEA, TA + dTA, EB + dEB, TB + dTB


def phase(E, T):
    """从 (E, T) 恢复相位角。"""
    return math.atan2(T / OMEGA_A, E)


def phase_diff(phiA, phiB):
    """有符号相位差，包裹到 [-pi, pi]。"""
    d = phiA - phiB
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


def run(TICKS=20000):
    EA, TA = 0.5, 0.0
    EB, TB = -0.3, 0.0    # B 初始与 A 略不同

    trail = []
    for tick in range(1, TICKS + 1):
        EA, TA, EB, TB = step(EA, TA, EB, TB)

        phiA = phase(EA, TA)
        phiB = phase(EB, TB)
        pd = phase_diff(phiA, phiB)

        trail.append({
            'tick': tick,
            'EA': EA, 'TA': TA,
            'EB': EB, 'TB': TB,
            'phiA': phiA, 'phiB': phiB,
            'phase_diff': pd,
            'abs_diff': abs(pd),
        })

    return trail


def main():
    print("跑 20000 tick 反相锁定对...")
    trail = run(20000)

    # 每 1000 tick 打印
    print("\n tick     EA      TA      EB      TB     phiA     phiB    diff(deg)")
    for r in trail[::1000]:
        deg = math.degrees(r['phase_diff'])
        print(f"{int(r['tick']):5d}  {r['EA']:+.3f}  {r['TA']:+.3f}  {r['EB']:+.3f}  {r['TB']:+.3f}  "
              f"{r['phiA']:+.3f}  {r['phiB']:+.3f}  {deg:+7.1f}")

    # 相位差统计
    diffs = [r['phase_diff'] for r in trail[1000:]]  # 去掉暂态
    abs_diffs = [abs(d) for d in diffs]
    print(f"\n相位差 统计（去掉前 1000 tick 暂态）:")
    print(f"  均值: {math.degrees(sum(diffs)/len(diffs)):.1f}°")
    print(f"  绝对值均值: {math.degrees(sum(abs_diffs)/len(abs_diffs)):.1f}°")
    print(f"  最大: {math.degrees(max(diffs)):.1f}°")
    print(f"  最小: {math.degrees(min(diffs)):.1f}°")
    print(f"  标准差: {math.degrees((sum((d-sum(diffs)/len(diffs))**2 for d in diffs)/len(diffs))**0.5):.1f}°")

    # 检查是否形成 180° 锁定
    near_180 = sum(1 for d in diffs if abs(abs(d) - math.pi) < 0.3)
    print(f"\n接近 180°（误差<0.3 rad）的比例: {near_180}/{len(diffs)} = {100*near_180/len(diffs):.1f}%")

    # 保存
    with open('experiment/antiphase_trail.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=trail[0].keys())
        w.writeheader()
        w.writerows(trail)
    print("\nCSV 已保存。")


if __name__ == "__main__":
    main()
