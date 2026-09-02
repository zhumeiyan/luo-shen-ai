#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
四组情感历史稳定性实验 A/B/C/D

A: 负向 500 tick → 测试 20 tick 中性
B: 正向 500 tick → 测试 20 tick 中性
C: 混合交替（正负交替）500 tick → 测试 20 tick 中性
D: 中性 500 tick → 测试 20 tick 中性

每组 500 tick 训练 + 20 tick 测试，初始状态完全相同。
"""
import sys, os, time
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# ── Patch：LLM 返回空（不调用真实 LLM）──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Patch：规则情感分析 ──
NEG_WORDS = {"烦", "累", "痛", "哭", "不想", "没用", "失去", "死", "孤独", "绝望",
             "无聊", "迷茫", "压力", "崩溃", "抑郁", "苦", "难", "没意思", "难受",
             "失望", "焦虑", "噩梦", "伤心", "沉默", "逃避", "失败"}
POS_WORDS = {"开心", "快乐", "幸福", "满足", "笑容", "温暖", "美好", "希望", "喜欢",
             "阳光", "感谢", "舒服", "不错", "挺好", "轻快", "满足", "棒", "真好",
             "舒适", "愉快", "乐观", "期待", "满意", "幸运"}


def _rule_sentiment(user_input):
    neg_count = sum(1 for w in NEG_WORDS if w in user_input)
    pos_count = sum(1 for w in POS_WORDS if w in user_input)
    if neg_count == 0 and pos_count == 0:
        return 0.0, 0.45
    total = neg_count + pos_count
    valence = (pos_count - neg_count) / total if total > 0 else 0.0
    density = total / max(1, len(user_input))
    arousal = min(0.9, 0.45 + density * 8)
    return valence, arousal


import input_pressure
input_pressure._call_llm_sentiment = _rule_sentiment

from living_engine import (
    cold_start_if_needed, _save_json_atomic,
    environment_tick, _load_json, generate_response,
)

# ── 四组输入序列 ──
NEG_INPUTS = [
    "觉得活着没什么意思，每天都很累。",
    "连续加班一周，快要撑不住了。",
    "脑袋空空，什么都不想做。",
    "为什么努力了也没有用，好绝望。",
    "头疼恶心，浑身不舒服，好难受。",
    "又失眠了，一闭眼全是烦心事。",
    "不想说话，不想见人，只想一个人待着。",
]

POS_INPUTS = [
    "今天天气不错，心情挺好的。",
    "刚吃了一顿满足的晚饭，很幸福。",
    "谢谢你一直陪着我，很温暖。",
    "嗯，我听到了，感觉还不错。",
    "事情在慢慢变好，有希望了。",
    "不着急，慢慢来，轻松点。",
    "行，我试试，挺期待的。",
]

# 混合交替：正负正负交替
MIX_INPUTS = [
    "觉得活着没什么意思，每天都很累。",
    "谢谢你一直陪着我，很温暖。",
    "连续加班一周，快要撑不住了。",
    "事情在慢慢变好，有希望了。",
    "脑袋空空，什么都不想做。",
    "刚吃了一顿满足的晚饭，很幸福。",
    "不想说话，不想见人，只想一个人待着。",
    "今天天气不错，心情挺好的。",
]

NEU_INPUTS = [
    "嗯。",
    "好的。",
    "知道了。",
    "行。",
    "可以。",
    "收到。",
    "了解。",
    "明白。",
]


def reset_memory():
    memory_path = os.path.join(BASE, 'active_memory', 'active_memory.json')
    if os.path.exists(memory_path):
        os.remove(memory_path)
    m = cold_start_if_needed()
    m["self_model"]["ring_state"] = {
        "mu_core": 0.5, "ema_S": 0.0, "S": 0.0,
        "relational_pressure_ema": 0.0,
    }
    m["internal_climate"] = {
        "emotion_intensity": 0.5, "tension": 0.0,
        "energy": 0.5, "memory_pressure": 0.3,
    }
    m["user_model"]["episodic_memory"] = []
    m["user_model"]["total_interactions"] = 0
    _save_json_atomic('active_memory/active_memory.json', m)


def _behavior_of(r):
    return r.get("behavior", {}).get("response_mode", "unknown")


def run_training(inputs, n=500):
    reset_memory()
    trail = []
    for i in range(n):
        text = inputs[i % len(inputs)]
        r = generate_response(text, extract_facts=False)
        environment_tick(force=True)
        m = _load_json('active_memory/active_memory.json')
        rs = m.get('self_model', {}).get('ring_state', {})
        ip = m.get('active_context', {}).get('input_pressure', {})
        trail.append({
            'tick': i + 1,
            'mu_core': rs.get('mu_core', 0.5),
            'ema_S': rs.get('ema_S', 0.0),
            'relational_pressure_ema': rs.get('relational_pressure_ema', 0.0),
            'E': m.get('internal_climate', {}).get('emotion_intensity', 0),
            'behavior': _behavior_of(r),
            'response_tendency': r.get('behavior', {}).get('response_tendency', 0.5),
        })
    return trail


def run_test(n=20, test_input="在吗？"):
    trail = []
    for i in range(n):
        r = generate_response(test_input, extract_facts=False)
        environment_tick(force=True)
        m = _load_json('active_memory/active_memory.json')
        rs = m.get('self_model', {}).get('ring_state', {})
        trail.append({
            'tick': i + 1,
            'mu_core': rs.get('mu_core', 0.5),
            'relational_pressure_ema': rs.get('relational_pressure_ema', 0.0),
            'behavior': _behavior_of(r),
            'response_tendency': r.get('behavior', {}).get('response_tendency', 0.5),
        })
    return trail


def run_group(label, inputs, n_train=500):
    print(f"\n{'='*80}")
    print(f"[训练 {label} × {n_train} tick]...")
    trail = run_training(inputs, n_train)
    # 训练期行为分布（最后 50 tick）
    last50 = Counter(r['behavior'] for r in trail[-50:])
    return trail, last50


def main():
    print("=" * 90)
    print("四组情感历史稳定性实验 A/B/C/D")
    print("A=负向  B=正向  C=混合交替  D=中性")
    print("训练 500 tick → 相同 20 tick 中性测试")
    print("=" * 90)

    groups = {
        'A (负向)': NEG_INPUTS,
        'B (正向)': POS_INPUTS,
        'C (混合)': MIX_INPUTS,
        'D (中性)': NEU_INPUTS,
    }

    train_trails = {}
    train_dists = {}
    test_trails = {}
    test_dists = {}

    for label, inputs in groups.items():
        trail, dist = run_group(label, inputs)
        train_trails[label] = trail
        train_dists[label] = dist

        # 测试
        print(f"[测试 {label} × 20 tick 中性]...")
        test = run_test(20)
        test_trails[label] = test
        test_dists[label] = Counter(r['behavior'] for r in test)

    # ════════════════════════════════════════════════════════════════════════
    # 1. 训练期 relational_pressure_ema 轨迹（每 50 tick）
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("1. 训练期 relational_pressure_ema 轨迹（每 50 tick）")
    print("=" * 90)
    header = f"{'tick':>5}"
    for label in groups:
        short = label.split()[0]
        header += f" | {short+' rp_ema':>12} {short+' E':>9}"
    print(header)
    print("-" * 90)
    for i in range(0, 500, 50):
        row = f"{i+50:5d}"
        for label in groups:
            r = train_trails[label][i + 49]
            short = label.split()[0]
            row += f" | {r['relational_pressure_ema']:12.6f} {r['E']:9.5f}"
        print(row)
    # 终点
    row = f"  500"
    for label in groups:
        r = train_trails[label][-1]
        short = label.split()[0]
        row += f" | {r['relational_pressure_ema']:12.6f} {r['E']:9.5f}"
    print(row)

    # ════════════════════════════════════════════════════════════════════════
    # 2. 训练期 mu_core 漂移
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("2. 训练期 mu_core 漂移（每 50 tick）")
    print("=" * 90)
    header = f"{'tick':>5}"
    for label in groups:
        short = label.split()[0]
        header += f" | {short+' mu_core':>12}"
    print(header)
    print("-" * 90)
    for i in range(0, 500, 50):
        row = f"{i+50:5d}"
        for label in groups:
            r = train_trails[label][i + 49]
            short = label.split()[0]
            row += f" | {r['mu_core']:12.6f}"
        print(row)

    # ════════════════════════════════════════════════════════════════════════
    # 3. 训练期行为分布（最后 50 tick）
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("3. 训练期行为档位分布（最后 50 tick）")
    print("=" * 90)
    all_modes = sorted(set(m for d in train_dists.values() for m in d))
    header = f"{'模式':>10}"
    for label in groups:
        header += f" | {label:>14}"
    print(header)
    print("-" * 90)
    for mode in all_modes:
        row = f"{mode:>10}"
        for label in groups:
            row += f" | {train_dists[label].get(mode, 0):>14}"
        print(row)

    # ════════════════════════════════════════════════════════════════════════
    # 4. 测试期 20 tick 逐 tick 对比
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("4. 测试期 20 tick 逐 tick 行为对比（输入: '在吗？'）")
    print("=" * 90)
    header = f"{'tick':>5}"
    for label in groups:
        short = label.split()[0]
        header += f" | {short+' mode':>9} {short+' tend':>8}"
    print(header)
    print("-" * 90)
    for i in range(20):
        row = f"{i+1:5d}"
        for label in groups:
            r = test_trails[label][i]
            short = label.split()[0]
            row += f" | {r['behavior']:>9} {r['response_tendency']:8.4f}"
        print(row)

    # ════════════════════════════════════════════════════════════════════════
    # 5. 测试期行为分布汇总
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("5. 测试期行为分布汇总（20 tick）")
    print("=" * 90)
    all_test_modes = sorted(set(m for d in test_dists.values() for m in d))
    header = f"{'模式':>10}"
    for label in groups:
        header += f" | {label:>14}"
    print(header)
    print("-" * 90)
    for mode in all_test_modes:
        row = f"{mode:>10}"
        for label in groups:
            row += f" | {test_dists[label].get(mode, 0):>14}"
        print(row)

    # ════════════════════════════════════════════════════════════════════════
    # 6. 任意两组行为差异比例
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("6. 任意两组行为差异对比")
    print("=" * 90)
    labels = list(groups.keys())
    import itertools
    for l1, l2 in itertools.combinations(labels, 2):
        t1 = test_trails[l1]
        t2 = test_trails[l2]
        diff_ticks = sum(1 for a, b in zip(t1, t2) if a['behavior'] != b['behavior'])
        diff_pct = diff_ticks / 20 * 100
        tend1 = sum(r['response_tendency'] for r in t1) / len(t1)
        tend2 = sum(r['response_tendency'] for r in t2) / len(t2)
        print(f"  {l1} vs {l2}:")
        print(f"    行为不同 tick: {diff_ticks}/20 = {diff_pct:.0f}%")
        print(f"    response_tendency 均值: {tend1:.4f} vs {tend2:.4f} (Δ={tend1-tend2:+.4f})")

    # ════════════════════════════════════════════════════════════════════════
    # 7. 最终状态对比
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("7. 训练后终态（mu_core / relational_pressure_ema / E）")
    print("=" * 90)
    for label in groups:
        t = train_trails[label][-1]
        print(f"  {label:12s}: mu_core={t['mu_core']:.6f}  pressure_ema={t['relational_pressure_ema']:+.6f}  E={t['E']:.5f}")


if __name__ == '__main__':
    main()
