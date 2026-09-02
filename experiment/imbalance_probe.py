#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内部失衡探针。

只用同一个 van der Pol 极限环方程，不靠任何外部输入。
跑 20000 tick，观察失衡读数是否自己出现起伏。

失衡读数的三个来源（连续函数，无 if-then）：
1. 二阶变化率（加速度） — E''² + T''² + N''²
2. 偏离近期均值的归一化距离
3. 偏离趋势是否在扩大（散度 vs 回归）

输出：imbalance ∈ [0,1]
"""

import math
import csv

# ── van der Pol 参数（与 living_engine.py 完全一致）──
MU_BASE = 0.5          # 0.5 + 0.3*L，L=0 时
DT = 0.08
K_MU = 0.1
ALPHA_M = 0.8
BETA_M = 0.8
GAMMA_N = 0.3
DELTA_N = 0.3


def vanderpol_step(E, T, N, M, dt=DT):
    """
    一步 van der Pol 积分（含 M 反馈稳定）。
    返回 (E', T', N', M')。
    """
    mu_eff = MU_BASE - K_MU * M
    dE = T * dt
    dT = (mu_eff * (1.0 - E * E) * T - E) * dt
    dM = (ALPHA_M * E * E - BETA_M * M) * dt
    dN = (GAMMA_N * (E * E + T * T) - DELTA_N * N) * dt
    E_new = E + dE
    T_new = T + dT
    N_new = N + dN
    M_new = M + dM
    return E_new, T_new, N_new, M_new


def compute_imbalance(buf, E, T, N, M, alpha=0.1):
    """
    失衡读数。buf 内含最近 K 个 (E,T,N,M) 样本。
    三项贡献：
      accel_term  — 归一化加速度（二阶）
      dev_term    — 偏离近期均值的距离
      spread_term — 偏离是否仍在扩大
    """
    K = len(buf)
    if K < 8:
        return 0.0, 0.0, 0.0, 0.0

    # ── 1. 加速度（E/T 的二阶）──
    dE_now = buf[-1][0] - buf[-2][0] if K >= 2 else 0.0
    dT_now = buf[-1][1] - buf[-2][1] if K >= 2 else 0.0
    dE_pre = buf[-2][0] - buf[-3][0] if K >= 3 else 0.0
    dT_pre = buf[-2][1] - buf[-3][1] if K >= 3 else 0.0
    ddE = dE_now - dE_pre
    ddT = dT_now - dT_pre
    accel_sq = ddE**2 + ddT**2
    accel_term = 1.0 - math.exp(-accel_sq / (DT**4 * 10 + 1e-9))

    # ── 2. 偏离近期均值 ──
    E_ma, T_ma, N_ma = 0.0, 0.0, 0.0
    w_sum = 0.0
    for i, (ei, ti, ni, mi) in enumerate(buf):
        w = (1 - alpha) ** (K - 1 - i)
        E_ma += w * ei
        T_ma += w * ti
        N_ma += w * ni
        w_sum += w
    E_ma /= w_sum
    T_ma /= w_sum
    N_ma /= w_sum

    dev_raw = math.sqrt((E - E_ma)**2 + (T - T_ma)**2 + (N - N_ma)**2)
    dev_term = 1.0 - math.exp(-dev_raw / 0.3)

    # ── 3. 偏离扩大 vs 回归（看 dev 序列的趋势）──
    devs = []
    for j in range(K):
        ej, tj, nj = buf[j][0], buf[j][1], buf[j][2]
        devs.append(math.sqrt((ej - E_ma)**2 + (tj - T_ma)**2 + (nj - N_ma)**2))
    # 用最近 1/3 vs 前 1/3 的 dev 均值比较
    third = K // 3
    if third >= 2:
        dev_recent = sum(devs[-third:]) / third
        dev_earlier = sum(devs[:third]) / third
        dev_change = dev_recent - dev_earlier
    else:
        dev_change = 0.0
    spread_term = 1.0 / (1.0 + math.exp(-8.0 * (dev_change - 0.05)))

    # ── 综合 ──
    imbalance = 0.4 * accel_term + 0.35 * dev_term + 0.25 * spread_term
    return imbalance, accel_term, dev_term, spread_term


def run(TICKS=20000):
    buf = []  # 存最近 60 个样本
    trail = []  # 全量日志

    E, T, N, M = 0.5, 0.0, 0.5, 0.0

    for tick in range(1, TICKS + 1):
        E_new, T_new, N_new, M_new = vanderpol_step(E, T, N, M)

        buf.append((E_new, T_new, N_new, M_new))
        if len(buf) > 60:
            buf.pop(0)

        imbalance, accel_term, dev_term, spread_term = compute_imbalance(
            buf, E_new, T_new, N_new, M_new
        )

        trail.append({
            'tick': tick,
            'E': E_new,
            'T': T_new,
            'N': N_new,
            'M': M_new,
            'imbalance': imbalance,
            'accel_term': accel_term,
            'dev_term': dev_term,
            'spread_term': spread_term,
        })

        E, T, N, M = E_new, T_new, N_new, M_new

    return trail


def main():
    print("跑 20000 tick ...")
    trail = run(20000)

    # 输出
    print(f"\n共 {len(trail)} tick")
    print(f"初始 imbalance: {trail[0]['imbalance']:.4f}")
    print(f"最终 imbalance: {trail[-1]['imbalance']:.4f}")

    # 峰值
    peak = max(trail, key=lambda r: r['imbalance'])
    valley = min(trail, key=lambda r: r['imbalance'])
    print(f"\n峰值 tick={peak['tick']}  imbalance={peak['imbalance']:.4f}  "
          f"E={peak['E']:.3f} T={peak['T']:.3f} N={peak['N']:.3f}  "
          f"accel={peak['accel_term']:.4f} dev={peak['dev_term']:.4f} spread={peak['spread_term']:.4f}")
    print(f"谷值 tick={valley['tick']}  imbalance={valley['imbalance']:.4f}  "
          f"E={valley['E']:.3f} T={valley['T']:.3f} N={valley['N']:.3f}")

    # 最后 200 tick
    print(f"\n── 最后 50 tick ──")
    print(f"{'tick':>6} {'E':>9} {'T':>9} {'N':>9} {'imb':>7} {'accel':>7} {'dev':>7} {'spread':>7}")
    for r in trail[-50:]:
        print(f"{r['tick']:6d} {r['E']:9.4f} {r['T']:9.4f} {r['N']:9.4f} "
              f"{r['imbalance']:7.4f} {r['accel_term']:7.4f} {r['dev_term']:7.4f} {r['spread_term']:7.4f}")

    # 检测显著起伏
    spikes = [r for r in trail if r['imbalance'] > 0.5]
    print(f"\nimbalance > 0.5 的 tick 数: {len(spikes)}")
    if spikes:
        # 按时间分组看有没有独立事件
        clusters = []
        cur = [spikes[0]]
        for s in spikes[1:]:
            if s['tick'] - cur[-1]['tick'] < 50:
                cur.append(s)
            else:
                clusters.append(cur)
                cur = [s]
        if cur:
            clusters.append(cur)
        print(f"其中独立起伏事件数: {len(clusters)}")
        for i, cl in enumerate(clusters[:5]):
            peak_cl = max(cl, key=lambda r: r['imbalance'])
            print(f"  事件 {i+1}: tick {cl[0]['tick']}-{cl[-1]['tick']}  "
                  f"持续 {len(cl)} tick  峰值={peak_cl['imbalance']:.4f} "
                  f"E={peak_cl['E']:.3f} T={peak_cl['T']:.3f}")

    # 保存 CSV
    with open('/mnt/data/catpaw/home/.meituan-catpaw/1079230951/desk_default_workspace/luo-shen-ai/experiment/imbalance_trail.csv',
              'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=trail[0].keys())
        w.writeheader()
        w.writerows(trail)
    print("\nCSV 已保存到 experiment/imbalance_trail.csv")


if __name__ == "__main__":
    main()
