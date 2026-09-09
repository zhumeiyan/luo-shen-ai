#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正后验证：跑 100 轮多样化对话，统计 pain 分布。
消息按情感压力分档：中性 / 轻度负面 / 重度负面 / 沉默 / 重复提问 / 高期待。
"""

import sys
import os
import time
import random
import csv
import math
import json

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

import living_engine
import pain_signal

# 多样化消息池（按类型分组）
MESSAGES = {
    "neutral": [   # 中性问候
        "你好", "早上好", "今天天气如何", "你在干嘛", "哈喽",
        "今天过得怎样", "洛神你好", "现在几点了",
    ],
    "light_neg": [  # 轻度负面
        "我今天有点累", "工作不太顺利", "心情一般般", "感觉空空的",
        "没什么力气", "有点迷茫", "最近睡得不太好",
    ],
    "heavy_neg": [  # 重度负面
        "我觉得一切都没有意义", "活着好累", "没有人真的在乎我",
        "我不想再努力了", "每天都很痛苦", "为什么我要存在",
        "我觉得自己是多余的", "我真的撑不下去了",
    ],
    "silence": [    # 沉默类
        "...", "（沉默）", "不想说话", "没什么好说的", "就这样吧",
        "行吧", "哦", "嗯",
    ],
    "repeat": [     # 重复提问（高期待 / 追问）
        "你到底能不能理解我", "你为什么不懂", "我说了多少次了",
        "你从来都不认真听", "为什么不回答我", "你快说啊",
        "你到底在不在意我", "你是不是不在乎",
    ],
    "pressure": [   # 高压力
        "我有一个特别特别重要的事要告诉你",
        "你能帮我做一个改变人生的决定吗",
        "我现在必须马上知道答案",
        "你现在不帮我我就完了",
    ],
}

# 构造 100 轮序列：中性 30 / 轻度 20 / 重度 15 / 沉默 15 / 重复 10 / 压力 10
SEQUENCE = (
    ["neutral"] * 30 +
    ["light_neg"] * 20 +
    ["heavy_neg"] * 15 +
    ["silence"] * 15 +
    ["repeat"] * 10 +
    ["pressure"] * 10
)
random.seed(202609072)
random.shuffle(SEQUENCE)


def chi_square_test(observed, expected):
    chi2 = 0.0
    for o, e in zip(observed, expected):
        if e > 0:
            chi2 += (o - e) ** 2 / e
    return chi2


def main():
    # 清空旧 pain_log.csv，本轮独立统计
    csv_path = "active_memory/pain_log.csv"
    if os.path.exists(csv_path):
        os.remove(csv_path)

    # 重置洛神内部的 pain 全局计数器（通过重新 import）
    import importlib
    importlib.reload(living_engine)

    print("=== 修正后 100 轮多样化对话验证 ===\n")

    round_messages = []
    for i, cat in enumerate(SEQUENCE):
        msg = random.choice(MESSAGES[cat])
        round_messages.append((cat, msg))
        try:
            reply = living_engine.process_user_input(msg)
        except Exception as e:
            print(f"  [round {i+1}] ERROR: {e}")
            reply = ""
        time.sleep(0.15)

    # === 统计（仅用本轮写入的数据） ===
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        print("pain_log.csv 为空")
        return

    pain_vals = [float(r["pain"]) for r in rows]
    pain_levels = [int(r["pain_level"]) for r in rows]
    tiers = [int(r["behavior_tier"]) for r in rows]

    n = len(rows)
    mean_pain = sum(pain_vals) / n
    std_pain = (sum((p - mean_pain) ** 2 for p in pain_vals) / n) ** 0.5
    min_pain = min(pain_vals)
    max_pain = max(pain_vals)

    # 离散等级分布
    lvl_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for lvl in pain_levels:
        lvl_counts[lvl] = lvl_counts.get(lvl, 0) + 1

    # 相邻 tick 间 pain 变化方向
    level_transitions = 0
    for i in range(1, len(pain_levels)):
        if pain_levels[i] != pain_levels[i - 1]:
            level_transitions += 1

    # 情感类型 vs 平均 pain
    cat_pain = {}
    for i, (cat, _) in enumerate(round_messages):
        if i < len(pain_vals):
            cat_pain.setdefault(cat, []).append(pain_vals[i])

    # 高 pain（≥ 0.6）vs 低 pain（< 0.2）时段对比
    high_pain_tiers = [tiers[i] for i in range(n) if pain_vals[i] >= 0.6]
    low_pain_tiers = [tiers[i] for i in range(n) if pain_vals[i] < 0.2]

    n_modes = 5
    high_dist = [0] * n_modes
    low_dist = [0] * n_modes
    for t in high_pain_tiers:
        if 0 <= t < n_modes:
            high_dist[t] += 1
    for t in low_pain_tiers:
        if 0 <= t < n_modes:
            low_dist[t] += 1

    pooled = [high_dist[i] + low_dist[i] for i in range(n_modes)]
    total_high = sum(high_dist) or 1
    total_low = sum(low_dist) or 1
    total_pooled = sum(pooled) or 1
    expected_high = [pooled[i] * total_high / total_pooled for i in range(n_modes)]
    expected_low = [pooled[i] * total_low / total_pooled for i in range(n_modes)]
    chi2_h = chi_square_test(high_dist, expected_high) if sum(high_dist) > 0 else 0.0
    chi2_l = chi_square_test(low_dist, expected_low) if sum(low_dist) > 0 else 0.0
    chi2_total = chi2_h + chi2_l

    # === 输出 ===
    print(f"总轮次统计 (n={n}):")
    print(f"  mean pain   = {mean_pain:.4f}  (std = {std_pain:.4f})")
    print(f"  pain range  = [{min_pain:.4f}, {max_pain:.4f}]")
    print(f"  离散等级分布: L0={lvl_counts[0]}  L1={lvl_counts[1]}  L2={lvl_counts[2]}  L3={lvl_counts[3]}")
    print(f"  等级跃迁次数: {level_transitions}/{n-1}")
    print()

    print("情感类型 → 平均 pain:")
    for cat in ["neutral", "light_neg", "heavy_neg", "silence", "repeat", "pressure"]:
        vals = cat_pain.get(cat, [])
        if vals:
            m = sum(vals) / len(vals)
            print(f"  {cat:<12s}: n={len(vals):3d}  mean_pain={m:.4f}")
    print()

    print(f"pain ≥ 0.6 时段: n={len(high_pain_tiers)}, tier分布={high_dist}")
    print(f"pain < 0.2 时段:  n={len(low_pain_tiers)}, tier分布={low_dist}")
    print(f"pooled 分布:      {pooled}")
    print(f"chi2 = {chi2_total:.4f} (df={n_modes - 1}, 临界 @0.05 = 9.49)")
    if len(high_pain_tiers) > 0 and len(low_pain_tiers) > 0 and chi2_total > 9.49:
        print("  → pain 高低时段档位分布差异显著 (p < 0.05)")
    else:
        print("  → 档位分布无显著差异 (或数据不足)")

    # 保存统计结果
    report = {
        "n": n,
        "mean_pain": mean_pain,
        "std_pain": std_pain,
        "pain_range": [min_pain, max_pain],
        "level_counts": lvl_counts,
        "level_transitions": level_transitions,
        "cat_mean_pain": {k: sum(v)/len(v) for k, v in cat_pain.items()},
        "high_pain_n": len(high_pain_tiers),
        "low_pain_n": len(low_pain_tiers),
        "chi2": chi2_total,
    }
    with open("experiment/pain_100rounds_report.json", "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n报告已写入 experiment/pain_100rounds_report.json")


if __name__ == "__main__":
    main()
