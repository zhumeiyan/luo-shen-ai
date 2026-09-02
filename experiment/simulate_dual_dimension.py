#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双维度行为选择预演模拟

输入：四组历史实验的 rp_ema 终值 + 测试期 response_tendency 均值
输出：每组在 5 档 + 压力质量双维度下的逐 tick 行为预测
"""
import math

# ── 方案参数 ──
_PRESSURE_K = 0.4
_PRESSURE_QUALITY_SCALE = 1.5   # rp_ema → pressure_quality 的缩放
_TOKEN_OFFSET_SCALE = 30         # pressure_quality → token 偏移的缩放
_BASE_TOKENS = [0, 25, 80, 180, 350]   # 5 档位 base tokens
_MODE_NAMES  = ["silent", "brief", "short", "normal", "engaged"]
_N_MODES = len(_MODE_NAMES)

def sigmoid(x):
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0

def select_behavior_dual(rp_ema, arousal_bias=0.0, tone_bias=0.0,
                         narrative_potential=0.0, phase=0.0):
    """模拟修改后的 _select_behavior"""
    # 预激活
    phase_bias = 0.03 * math.sin(phase)
    response_pre = (arousal_bias
                    + 0.5 * tone_bias
                    + 5.0 * narrative_potential
                    + phase_bias
                    + _PRESSURE_K * rp_ema)
    tend = sigmoid(response_pre)

    # 档位索引（floor-based）
    mode_idx = int(tend * _N_MODES)
    if mode_idx >= _N_MODES:
        mode_idx = _N_MODES - 1

    # 压力质量（连续，不受 sigmoid 压缩）
    pq = _PRESSURE_QUALITY_SCALE * rp_ema
    if pq > 1.0:
        pq = 1.0
    elif pq < -1.0:
        pq = -1.0

    # max_tokens = base + 偏移（连续变化）
    base = _BASE_TOKENS[mode_idx]
    offset = int(_TOKEN_OFFSET_SCALE * pq)   # int 截断取整
    max_tokens = base + offset
    if max_tokens < 0:
        max_tokens = 0

    return {
        "mode_idx": mode_idx,
        "mode_name": _MODE_NAMES[mode_idx],
        "tendency": round(tend, 4),
        "pressure_quality": round(pq, 4),
        "base_tokens": base,
        "token_offset": offset,
        "max_tokens": max_tokens,
    }


def main():
    # 四组实验终态
    groups = {
        "A (负向)": {"rp_ema": -0.683162, "tend_original": 0.4513},
        "B (正向)": {"rp_ema": +0.774071, "tend_original": 0.5681},
        "C (混合)": {"rp_ema": +0.063280, "tend_original": 0.5028},
        "D (中性)": {"rp_ema": +0.000000, "tend_original": 0.4982},
    }

    print("=" * 100)
    print("双维度行为选择预演（使用四组历史实验 rp_ema 终值）")
    print("=" * 100)
    print()

    # ── 1. 各组在 phase=0（典型）下的稳态预测 ──
    print("§1 稳态预测 (phase=0)")
    print("-" * 100)
    header = f"{'组':14s} | {'rp_ema':>9s} | {'pre':>7s} | {'tend':>7s} | {'mode_idx':>4s} | {'mode':>8s} | {'pq':>7s} | {'base':>5s} | {'offset':>6s} | {'max_tok':>7s}"
    print(header)
    print("-" * 100)

    results = {}
    for label, info in groups.items():
        r = select_behavior_dual(rp_ema=info["rp_ema"], phase=0.0)
        pre = r["tendency"]  # reconstructed
        pre_value = math.log(r["tendency"] / (1 - r["tendency"])) if 0 < r["tendency"] < 1 else 0
        print(f"{label:14s} | {info['rp_ema']:9.4f} | {pre_value:7.4f} | {r['tendency']:7.4f} | "
              f"{r['mode_idx']:4d} | {r['mode_name']:>8s} | {r['pressure_quality']:7.4f} | "
              f"{r['base_tokens']:5d} | {r['token_offset']:6d} | {r['max_tokens']:7d}")
        results[label] = r

    # ── 2. 边界连续性：tend 从 0.43 到 0.51 连续扫过 ──
    print()
    print("§2 连续性扫描：rp_ema 从 -0.7 到 +0.8（覆盖四组实际范围）")
    print("-" * 100)
    print(f"{'rp_ema':>8s} | {'pre':>7s} | {'tend':>7s} | {'idx':>3s} | {'mode':>8s} | {'pq':>6s} | {'base':>4s} | {'offset':>6s} | {'tokens':>6s}")
    print("-" * 100)

    for rp in [-0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 0.0,
               0.05, 0.063, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.77, 0.8]:
        r = select_behavior_dual(rp_ema=rp, phase=0.0)
        pre_val = math.log(r["tendency"] / (1 - r["tendency"])) if 0 < r["tendency"] < 1 else 0
        print(f"{rp:8.3f} | {pre_val:7.4f} | {r['tendency']:7.4f} | {r['mode_idx']:3d} | "
              f"{r['mode_name']:>8s} | {r['pressure_quality']:6.3f} | {r['base_tokens']:4d} | "
              f"{r['token_offset']:6d} | {r['max_tokens']:6d}")

    # ── 3. C vs D 在 phase 微小变化下的响应 ──
    print()
    print("§3 C/D 微小差异在 phase 变动下的最大分离")
    print("-" * 100)
    print(f"{'rp_ema':>8s} | {'phase':>6s} | {'tend':>7s} | {'mode':>8s} | {'pq':>7s} | {'tokens':>6s}")
    print("-" * 100)

    for rp, label in [(0.063, "C"), (0.0, "D")]:
        for phase in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
            r = select_behavior_dual(rp_ema=rp, phase=phase)
            print(f"{rp:8.3f} | {phase:6.2f} | {r['tendency']:7.4f} | {r['mode_name']:>8s} | "
                  f"{r['pressure_quality']:7.4f} | {r['max_tokens']:6d}")
        print("  --")

    # ── 4. 边界跳变检查 ──
    print()
    print("§4 边界跳变分析：寻找 mode 切换点的具体 rp_ema")
    print("-" * 100)
    # mode 切换发生在 tend = 1/5, 2/5, 3/5, 4/5
    # 即 pre = sigmoid^{-1}(k/5)
    boundaries = []
    for k in range(1, 5):
        tend_boundary = k / 5.0
        # pre = ln(tend/(1-tend))
        if 0 < tend_boundary < 1:
            pre_boundary = math.log(tend_boundary / (1 - tend_boundary))
        else:
            pre_boundary = None
        # pre = 0 + 0 + 0 + 0 + 0.4 * rp  (assuming phase=0, arousal=0, tone=0, narrative=0)
        if pre_boundary is not None:
            rp_boundary = pre_boundary / _PRESSURE_K
            boundaries.append((k, tend_boundary, pre_boundary, rp_boundary))
            print(f"mode {k-1} → {k} 边界: tend={tend_boundary:.3f}, pre={pre_boundary:+.4f}, "
                  f"rp_ema(boundary)={rp_boundary:+.4f}")

    print()
    print("四组实际 rp_ema 距离最近边界的距离：")
    for label, info in groups.items():
        for k, tb, pb, rb in boundaries:
            dist = abs(info["rp_ema"] - rb)
            if dist < 0.15:
                print(f"  {label} (rp={info['rp_ema']:+.4f}) 距 mode {k-1}/{k} 边界仅 {dist:.4f}")

    # ── 5. 最终结论 ──
    print()
    print("=" * 100)
    print("§5 结论")
    print("=" * 100)
    print()
    print("四组稳态输出:")
    for label, info in groups.items():
        r = results[label]
        print(f"  {label:12s} → mode={r['mode_name']:>8s}, max_tokens={r['max_tokens']:3d}, pq={r['pressure_quality']:+.3f}")
    print()

    a_tok = results["A (负向)"]["max_tokens"]
    b_tok = results["B (正向)"]["max_tokens"]
    c_tok = results["C (混合)"]["max_tokens"]
    d_tok = results["D (中性)"]["max_tokens"]
    c_mode = results["C (混合)"]["mode_name"]
    d_mode = results["D (中性)"]["mode_name"]

    print(f"  C 档位: {c_mode}, D 档位: {d_mode}  → ", end="")
    if c_mode == d_mode:
        print("同一档位（连续令牌差异区分）")
    else:
        print("不同档位")
    print(f"  C tokens={c_tok}, D tokens={d_tok}, 差值={c_tok - d_tok}")
    print(f"  A vs B: a_tok={a_tok}, b_tok={b_tok}, 差值={b_tok - a_tok}")
    print()

    if a_tok == 0:
        print("  ⚠️  A 组 max_tokens = 0（彻底沉默）。这是一个设计选择：")
        print("     → 如果意图是'负向历史让她完全不想说话'，这是合理的")
        print("     → 如果意图是'负向历史只让她更简短但不至于不说话'，需设置 min_tokens ≥ 5")
        print("     → 建议：设置 A 组 offset 下界为 -base + min_reply，保证至少回复 1 句简短的话")


if __name__ == "__main__":
    main()
