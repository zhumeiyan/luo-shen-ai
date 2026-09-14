#!/usr/bin/env python3
"""遁一 — 三轴骨架执行。

a = (时间, 地点, 人物)  -> 向量
b = (时间, 地点, 人物)  -> 向量
Δ = b − a
Σ = a + b
⊗ = ∫(Δ, Σ)    append-only
τ 读 ⊗ → 浮    全历史 |Δ| 均值，所见即浮
(a, b) ⟲ ⊗    本拍(Δ, Σ) 直接变下拍(a, b)

禁止：if-then、随机、硬编码分支、词库匹配
"""
import math
import time


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def mean(v):
    return sum(v) / len(v)


def tau_read(tensor):
    """τ 读 ⊗ → 浮：整条⊗，全历史 |Δ| 均值。所见即浮，非当下单拍。"""
    return mean([e["d_norm"] for e in tensor])


def advance(delta, sigma):
    """⟲：本拍 (Δ, Σ) 直接变下拍 (a, b)。无分支。"""
    return list(delta), list(sigma)


def main():
    # ---- 初值：每轴 a ≠ b，非退化 ----
    a = [1.0, 0.5, 0.3]
    b = [2.0, 0.7, 0.9]
    N = 200

    tensor = []
    floats = []
    t0 = time.time()

    for n in range(N):
        delta = [b[i] - a[i] for i in range(3)]
        sigma = [a[i] + b[i] for i in range(3)]
        d_norm = norm(delta)
        s_norm = norm(sigma)
        tensor.append({
            "step": n,
            "a": a[:],
            "b": b[:],
            "delta": delta,
            "sigma": sigma,
            "d_norm": d_norm,
            "s_norm": s_norm,
            "dt_ms": round((time.time() - t0) * 1000, 3),
        })
        floats.append(tau_read(tensor))
        a, b = advance(delta, sigma)

    print("=" * 80)
    print("遁一 · 原始步表")
    print("=" * 80)
    print(f"a0 = {tensor[0]['a']}")
    print(f"b0 = {tensor[0]['b']}")
    print(f"N  = {N}")
    print(f"elapsed_ms = {round((time.time() - t0) * 1000, 3)}")
    print(f"a_final = {[round(x, 6) for x in a]}")
    print(f"b_final = {[round(x, 6) for x in b]}")

    print()
    print("-" * 80)
    print(f"{'step':>4}  {'a(t,l,p)':>32}  {'b(t,l,p)':>32}  "
          f"{'Δ':>20}  {'Σ':>20}  {'|Δ|':>8}  {'|Σ|':>8}  {'τ':>10}")
    print("-" * 80)
    for entry in tensor:
        a_str = f"({entry['a'][0]:+.4f},{entry['a'][1]:+.4f},{entry['a'][2]:+.4f})"
        b_str = f"({entry['b'][0]:+.4f},{entry['b'][1]:+.4f},{entry['b'][2]:+.4f})"
        d_str = f"({entry['delta'][0]:+.4f},{entry['delta'][1]:+.4f},{entry['delta'][2]:+.4f})"
        s_str = f"({entry['sigma'][0]:+.4f},{entry['sigma'][1]:+.4f},{entry['sigma'][2]:+.4f})"
        print(f"{entry['step']:4d}  {a_str:>32}  {b_str:>32}  "
              f"{d_str:>20}  {s_str:>20}  {entry['d_norm']:8.4f}  "
              f"{entry['s_norm']:8.4f}  {floats[entry['step']]:+10.6f}")

    d_norms = [e["d_norm"] for e in tensor]
    s_norms = [e["s_norm"] for e in tensor]

    print()
    print("=" * 80)
    print("⊗ 统计")
    print("=" * 80)
    print(f"entries              = {len(tensor)}")
    print(f"|Δ|  mean            = {mean(d_norms):.6f}")
    print(f"|Δ|  first5 mean     = {mean(d_norms[:5]):.6f}")
    print(f"|Δ|  last5  mean     = {mean(d_norms[-5:]):.6f}")
    print(f"|Σ|  mean            = {mean(s_norms):.6f}")
    print(f"|Σ|  first5 mean     = {mean(s_norms[:5]):.6f}")
    print(f"|Σ|  last5  mean     = {mean(s_norms[-5:]):.6f}")
    print(f"τ   mean             = {mean(floats):+.6f}")
    print(f"τ   first5 mean      = {mean(floats[:5]):+.6f}")
    print(f"τ   last5  mean      = {mean(floats[-5:]):+.6f}")

    print()
    print("=" * 80)
    print("末段逐值  steps 180..199")
    print("=" * 80)
    print(f"{'step':>4}  {'Δ[0]':>11}  {'Δ[1]':>11}  {'Δ[2]':>11}  "
          f"{'Σ[0]':>11}  {'Σ[1]':>11}  {'Σ[2]':>11}  {'|Δ|':>10}  {'|Σ|':>10}  {'τ':>14}")
    for entry in tensor[180:]:
        print(f"{entry['step']:4d}  "
              f"{entry['delta'][0]:+11.4f}  {entry['delta'][1]:+11.4f}  {entry['delta'][2]:+11.4f}  "
              f"{entry['sigma'][0]:+11.4f}  {entry['sigma'][1]:+11.4f}  {entry['sigma'][2]:+11.4f}  "
              f"{entry['d_norm']:10.4f}  {entry['s_norm']:10.4f}  {floats[entry['step']]:+14.6f}")


if __name__ == "__main__":
    main()
