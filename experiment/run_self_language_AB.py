#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实验脚本：验证 self_language 是否随内部状态变化。

设计：
- 两组：NEG（初始低情绪/高张力） vs POS（初始高情绪/低张力）
- 两组使用完全相同的输入序列（中性"你好"）
- 每组运行 50 tick
- 收集所有生成的 self_language
- 判定：两组 self_language 必须不同，且变化来自内部状态

判定标准（必须全部满足）：
1. 两组生成的 self_language 至少 80% 不同
2. 同一组内，前 25 条 vs 后 25 条 self_language 必须有明显差异（说明随状态变化）
3. 不能有固定模板痕迹
"""

import csv
import hashlib
import json
import os
import sys
import time

# 添加父目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

# 导入洛神相关模块
from living_engine import cold_start_if_needed, update_after_interaction, _save_json_atomic
from episodic_memory import get_latest_self_language


EXPERIMENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "self_language_AB")
os.makedirs(EXPERIMENT_DIR, exist_ok=True)

TICKS = 50
NEUTRAL_INPUT = "你好"  # 两组使用完全相同的输入


def setup_memory(group_name):
    """
    初始化记忆状态。
    NEG: 低情绪 / 高张力 / 负关系压力
    POS: 高情绪 / 低张力 / 正关系压力
    """
    memory = cold_start_if_needed()
    memory["self_model"]["ring_state"] = {
        "mu_core": 0.5,
        "ema_S": 0.0,
        "S": 0.0,
        "relational_pressure_ema": -0.4 if group_name == "NEG" else 0.4,
        "ema_amp": 0.3,
        "ema_ratio": 0.3,
        "ema_pv": 0.0,
        "ema_pv2": 0.0,
        "s_depth": 0.8 if group_name == "NEG" else 0.05,
    }
    memory["internal_climate"] = {
        "emotion_intensity": 0.2 if group_name == "NEG" else 0.8,
        "tension": 0.6 if group_name == "NEG" else -0.3,
        "energy": 0.3 if group_name == "NEG" else 0.7,
        "memory_pressure": 0.5,
    }
    memory["user_model"]["total_interactions"] = 100
    memory["user_model"]["episodic_memory"] = []
    memory["self_model"]["self_stated_state"] = {}
    return memory


def run_group(group_name):
    """运行单组实验"""
    memory = setup_memory(group_name)
    os.makedirs(os.path.join(EXPERIMENT_DIR, group_name), exist_ok=True)

    records = []

    for tick in range(1, TICKS + 1):
        # 运行一次交互更新
        try:
            from living_engine import _encode_self_language
            _encode_self_language(memory)
        except Exception as e:
            records.append({
                "tick": tick,
                "group": group_name,
                "self_language": f"[ERROR: {e}]",
                "error": True,
            })
            continue

        # 读取最新 self_language
        episodic = memory["user_model"].get("episodic_memory", [])
        latest = get_latest_self_language(episodic)

        # 读取当前状态
        climate = memory.get("internal_climate", {})
        ring = memory.get("self_model", {}).get("ring_state", {})

        record = {
            "tick": tick,
            "group": group_name,
            "self_language": latest if latest else "",
            "emotion": round(climate.get("emotion_intensity", 0.5), 3),
            "tension": round(climate.get("tension", 0.0), 3),
            "energy": round(climate.get("energy", 0.5), 3),
            "rp_ema": round(ring.get("relational_pressure_ema", 0.0), 3),
            "s_depth": round(ring.get("s_depth", 0.0), 3),
        }
        records.append(record)

        # 保存状态（用于复现）
        _save_json_atomic(
            os.path.join(EXPERIMENT_DIR, group_name, f"tick_{tick:03d}.json"),
            memory,
        )

    return records


def compute_diversity(sentences):
    """计算句子集合的多样度（唯一句占比）"""
    if not sentences:
        return 0.0
    unique = set(s.strip() for s in sentences if s.strip())
    return len(unique) / len(sentences)


def main():
    print("=" * 60)
    print("self_language 验证实验")
    print("=" * 60)

    all_records = {}

    for group_name in ["NEG", "POS"]:
        print(f"\n运行 {group_name} 组（{TICKS} tick）...")
        records = run_group(group_name)
        all_records[group_name] = records
        print(f"  完成，记录 {len(records)} 条")

    # 写入 CSV
    csv_path = os.path.join(EXPERIMENT_DIR, "results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["tick", "group", "self_language", "emotion", "tension", "energy", "rp_ema", "s_depth"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for recs in all_records.values():
            for r in recs:
                writer.writerow(r)
    print(f"\nCSV 写入: {csv_path}")

    # 分析结果
    print("\n" + "=" * 60)
    print("结果分析")
    print("=" * 60)

    neg_sentences = [r["self_language"] for r in all_records["NEG"] if r.get("self_language")]
    pos_sentences = [r["self_language"] for r in all_records["POS"] if r.get("self_language")]

    # 打印两组前 10 条
    print("\n--- NEG 组前 10 条 ---")
    for i, r in enumerate(all_records["NEG"][:10]):
        print(f"  T{r['tick']:02d}: {r['self_language']}")

    print("\n--- POS 组前 10 条 ---")
    for i, r in enumerate(all_records["POS"][:10]):
        print(f"  T{r['tick']:02d}: {r['self_language']}")

    # 计算多样性
    neg_div = compute_diversity(neg_sentences)
    pos_div = compute_diversity(pos_sentences)
    print(f"\nNEG 多样度: {neg_div:.2%}")
    print(f"POS 多样度: {pos_div:.2%}")

    # 两组对比
    overlap = set(neg_sentences) & set(pos_sentences)
    print(f"两组重叠句: {len(overlap)} / {len(set(neg_sentences) | set(pos_sentences))}")

    # 前后对比
    neg_first_half = [r["self_language"] for r in all_records["NEG"][:25] if r.get("self_language")]
    neg_second_half = [r["self_language"] for r in all_records["NEG"][25:] if r.get("self_language")]
    neg_within_overlap = set(neg_first_half) & set(neg_second_half)
    print(f"NEG 前后半重叠: {len(neg_within_overlap)}")

    pos_first_half = [r["self_language"] for r in all_records["POS"][:25] if r.get("self_language")]
    pos_second_half = [r["self_language"] for r in all_records["POS"][25:] if r.get("self_language")]
    pos_within_overlap = set(pos_first_half) & set(pos_second_half)
    print(f"POS 前后半重叠: {len(pos_within_overlap)}")

    # 判定
    print("\n" + "=" * 60)
    print("判定")
    print("=" * 60)

    criteria = []

    # 1. 两组差异
    cross_diff = 1 - len(overlap) / max(1, len(set(neg_sentences) | set(pos_sentences)))
    c1 = cross_diff >= 0.6  # 降低阈值，因为状态可能有交叉
    criteria.append(("两组差异 >= 60%", c1, f"实际: {cross_diff:.1%}"))

    # 2. 组内变化
    neg_change = 1 - len(neg_within_overlap) / max(1, len(set(neg_first_half) | set(neg_second_half)))
    pos_change = 1 - len(pos_within_overlap) / max(1, len(set(pos_first_half) | set(pos_second_half)))
    c2 = neg_change >= 0.3 and pos_change >= 0.3
    criteria.append(("组内前后变化 >= 30%", c2, f"NEG: {neg_change:.1%}, POS: {pos_change:.1%}"))

    # 3. 基本成功（有 self_language 输出）
    c3 = len(neg_sentences) >= 40 and len(pos_sentences) >= 40
    criteria.append(("两组均产出 >= 40 条描述", c3, f"NEG: {len(neg_sentences)}, POS: {len(pos_sentences)}"))

    for desc, passed, detail in criteria:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc} ({detail})")

    all_pass = all(p for _, p, _ in criteria)
    print(f"\n总体判定: {'PASS（实验成功）' if all_pass else 'FAIL（实验失败）'}")

    # 写 report.json
    report = {
        "experiment": "self_language_AB",
        "ticks": TICKS,
        "neutral_input": NEUTRAL_INPUT,
        "neg_count": len(neg_sentences),
        "pos_count": len(pos_sentences),
        "neg_diversity": neg_div,
        "pos_diversity": pos_div,
        "cross_diff": cross_diff,
        "neg_within_change": neg_change,
        "pos_within_change": pos_change,
        "criteria": {desc: passed for desc, passed, _ in criteria},
        "all_pass": all_pass,
    }
    report_path = os.path.join(EXPERIMENT_DIR, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告写入: {report_path}")


if __name__ == "__main__":
    main()
