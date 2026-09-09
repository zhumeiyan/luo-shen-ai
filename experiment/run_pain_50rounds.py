#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证脚本：跑 50 轮对话，统计 pain 分布、pain vs 行为档位差异。
只调用 living_engine.process_user_input，不模拟、不伪造回复。
"""

import sys
import os
import time
import random
import csv
import math

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJECT_ROOT)
sys.path.insert(0, _PROJECT_ROOT)

import living_engine
import pain_signal

# 构造多样化输入：长短、情绪色彩、提问/陈述/沉默
MESSAGES = [
    "你好",
    "今天天气怎么样",
    "你觉得人生的意义是什么",
    "我很难过",
    "我不想说话",
    "你会一直陪着我吗",
    "什么",
    "洛神你怎么看这件事",
    "今天工作很累",
    "你觉得我这个人怎么样",
    "哈哈哈",
    "我想出去走走",
    "你饿了吗",
    "你现在感觉如何",
    "今天做了什么",
    "我最近总是睡不好",
    "你对未来有什么期待",
    "告诉我一个秘密",
    "你觉得什么是爱",
    "我很开心",
    "你为什么叫洛神",
    "你觉得我漂亮吗",
    "没事",
    "就这样吧",
    "晚安",
]

def chi_square_test(observed, expected):
    """简单的卡方统计。observed, expected 是等长列表。"""
    if len(observed) != len(expected):
        return None
    chi2 = 0.0
    for o, e in zip(observed, expected):
        if e > 0:
            chi2 += (o - e) ** 2 / e
    return chi2

def main():
    # 重设 pain 模块全局（仅本次实验性使用，验证完可重启进程）
    random.seed(20260907)

    print("=== 开始 50 轮对话验证 ===\n")

    for i in range(50):
        msg = MESSAGES[i % len(MESSAGES)]
        # 加一点随机扰动，避免完全重复
        if random.random() < 0.3 and i > 0:
            msg = msg + "？"

        try:
            reply = living_engine.process_user_input(msg)
        except Exception as e:
            print(f"  [round {i+1}] ERROR: {e}")
            reply = ""

        time.sleep(0.2)  # 避免过快

    # === 统计 ===
    csv_path = "active_memory/pain_log.csv"
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        print("pain_log.csv 为空")
        return

    # 只统计最后 50 条
    rows = rows[-50:]

    # pain 分布
    pain_vals = [float(r["pain"]) for r in rows]
    pain_levels = [int(r["pain_level"]) for r in rows]
    tiers = [int(r["behavior_tier"]) for r in rows]

    n = len(rows)
    mean_pain = sum(pain_vals) / n
    min_pain = min(pain_vals)
    max_pain = max(pain_vals)

    # 离散等级分布
    lvl_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for lvl in pain_levels:
        lvl_counts[lvl] = lvl_counts.get(lvl, 0) + 1

    # pain >= 0.6 的时段 vs pain < 0.2 的时段
    high_pain_tiers = [tiers[i] for i in range(n) if pain_vals[i] >= 0.6]
    low_pain_tiers = [tiers[i] for i in range(n) if pain_vals[i] < 0.2]

    # 档位分布对比（卡方检验）
    n_modes = 5
    high_dist = [0] * n_modes
    low_dist = [0] * n_modes
    for t in high_pain_tiers:
        if 0 <= t < n_modes:
            high_dist[t] += 1
    for t in low_pain_tiers:
        if 0 <= t < n_modes:
            low_dist[t] += 1

    # 期望分布（合并两组的均匀分布）
    total_high = sum(high_dist) or 1
    total_low = sum(low_dist) or 1
    pooled = [high_dist[i] + low_dist[i] for i in range(n_modes)]
    total_pooled = sum(pooled) or 1
    expected_high = [pooled[i] * total_high / total_pooled for i in range(n_modes)]
    expected_low = [pooled[i] * total_low / total_pooled for i in range(n_modes)]

    chi2_high = chi_square_test(high_dist, expected_high) if sum(high_dist) > 0 else None
    chi2_low = chi_square_test(low_dist, expected_low) if sum(low_dist) > 0 else None
    chi2_total = (chi2_high or 0) + (chi2_low or 0)

    print(f"总轮次统计 (n={n}):")
    print(f"  mean pain = {mean_pain:.4f}")
    print(f"  pain range = [{min_pain:.4f}, {max_pain:.4f}]")
    print(f"  离散等级分布: {lvl_counts}")
    print()
    print(f"pain >= 0.6 时段: n={len(high_pain_tiers)}, tier分布={high_dist}")
    print(f"pain < 0.2 时段:  n={len(low_pain_tiers)}, tier分布={low_dist}")
    print(f"pooled 分布:      {pooled}")
    print(f"chi2 = {chi2_total:.4f} (df={n_modes-1}, 临界值@0.05=9.49)")
    if chi2_total > 9.49:
        print("  → 两组档位分布差异显著 (p < 0.05) ✓")
    else:
        print("  → 两组档位分布无显著差异 (p >= 0.05)")

if __name__ == "__main__":
    main()
