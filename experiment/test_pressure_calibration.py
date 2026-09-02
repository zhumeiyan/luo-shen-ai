#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
压力项系数校准扫描

扫描 _PRESSURE_K = 0.1, 0.2, 0.4 三个档位。
对每个系数：
  1. 训练 A（负向 500 tick）+ B（正向 500 tick）
  2. 测试 A/B 各 20 tick（相同中性输入）
  3. 记录每系数下 A/B 行为分布和 response_tendency 差异

关键不变量：
  - relational_pressure_ema 由 _apply_input_pressure 累积（与 K 无关）
  - _select_behavior 用 K * pressure_ema 影响档位选择
  - 目标：找最小 K 使 A/B 测试期行为分布差异 ≥ 30%
"""
import sys, os, time, json
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# ── Patch LLM（避免 API 调用）──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Patch sentiment analysis（确定性规则）──
NEG_WORDS = {"烦", "累", "痛", "哭", "不想", "没用", "死", "孤独", "绝望",
             "无聊", "迷茫", "压力", "崩溃", "抑郁", "苦", "难受", "失望",
             "焦虑", "噩梦", "伤心", "逃避", "失败", "撑不住", "失眠",
             "疲惫", "消极", "绝望", "没意思"}
POS_WORDS = {"开心", "快乐", "幸福", "满足", "笑容", "温暖", "美好", "希望",
             "喜欢", "阳光", "感谢", "舒服", "不错", "挺好", "轻快", "棒",
             "舒适", "愉快", "乐观", "期待", "满意", "幸运", "好", "爱"}


def rule_sentiment(text):
    neg = sum(1 for w in NEG_WORDS if w in text)
    pos = sum(1 for w in POS_WORDS if w in text)
    if neg == 0 and pos == 0:
        return 0.0, 0.45
    total = neg + pos
    valence = (pos - neg) / total if total > 0 else 0.0
    density = total / max(1, len(text))
    arousal = min(0.9, 0.45 + density * 8)
    return valence, arousal


import input_pressure
input_pressure._call_llm_sentiment = rule_sentiment

import living_engine as le
from living_engine import (
    cold_start_if_needed, _save_json_atomic,
    environment_tick, _load_json,
)

# ── 输入序列 ──
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


def reset_memory():
    memory_path = os.path.join(BASE, 'active_memory', 'active_memory.json')
    if os.path.exists(memory_path):
        os.remove(memory_path)
    m = cold_start_if_needed()
    self_model = m.get("self_model", {})
    self_model["ring_state"] = {
        "mu_core": 0.5, "ema_S": 0.0, "S": 0.0, "relational_pressure_ema": 0.0
    }
    m["self_model"] = self_model
    m["internal_climate"] = {
        "emotion_intensity": 0.5, "tension": 0.0,
        "energy": 0.5, "memory_pressure": 0.3,
    }
    user_model = m.get("user_model", {})
    user_model["episodic_memory"] = []
    user_model["total_interactions"] = 0
    m["user_model"] = user_model
    _save_json_atomic('active_memory/active_memory.json', m)


def _behavior_of(r):
    return r.get("behavior", {}).get("response_mode", "unknown")


def behavior_mode_for_text(text, extract=True):
    """单 tick 交互，返回行为档位。"""
    r = le.generate_response(text, extract_facts=extract)
    environment_tick(force=True)
    return _behavior_of(r)


def train_and_test(inputs, n=500):
    reset_memory()
    mode_counter = Counter()
    last_pressure = 0.0
    last_pre = 0.0
    for i in range(n):
        text = inputs[i % len(inputs)]
        r = le.generate_response(text, extract_facts=True)
        environment_tick(force=True)
        mode = _behavior_of(r)
        mode_counter[mode] += 1
        if i == n - 1:
            m = _load_json('active_memory/active_memory.json')
            rs = m.get('self_model', {}).get('ring_state', {})
            last_pressure = rs.get('relational_pressure_ema', 0.0)
            last_pre = r.get('behavior', {}).get('response_tendency', 0.5)
    return mode_counter, last_pressure


def run_test(test_input="在吗？", n=20):
    """跑 n tick 测试，返回逐 tick 记录。"""
    trail = []
    for i in range(n):
        r = le.generate_response(test_input, extract_facts=False)
        environment_tick(force=True)
        m = _load_json('active_memory/active_memory.json')
        rs = m.get('self_model', {}).get('ring_state', {})
        trail.append({
            'tick': i + 1,
            'mode': _behavior_of(r),
            'pressure_ema': rs.get('relational_pressure_ema', 0.0),
            'response_tendency': r.get('behavior', {}).get('response_tendency', 0.5),
            'reply': r.get('reply', ''),
        })
    return trail


def main():
    coefficients = [0.1, 0.2, 0.4]
    results = {}

    print("=" * 80)
    print("压力项系数校准扫描")
    print("扫描 K =", coefficients)
    print("每个系数：A 训练(500 neg) + B 训练(500 pos) + A/B 测试(20 neutral)")
    print("=" * 80)

    for k in coefficients:
        print(f"\n{'=' * 80}")
        print(f"[_PRESSURE_K = {k}]")
        print(f"{'=' * 80}")
        le._PRESSURE_K = k

        # ── Phase 1: Train A (负向) ──
        print(f"[K={k}] Phase 1: 训练 A（负向 × 500）...")
        train_a_modes, train_a_pressure = train_and_test(NEG_INPUTS, 500)
        print(f"  训练 A 行为分布: {dict(train_a_modes)}")
        print(f"  训练 A 最终压力 EMA: {train_a_pressure:+.6f}")

        # ── Phase 2: Test A ──
        print(f"[K={k}] Phase 2: 测试 A（20 tick）...")
        test_a = run_test("在吗？", 20)

        # ── Phase 3: Train B (正向) ──
        print(f"[K={k}] Phase 3: 训练 B（正向 × 500）...")
        train_b_modes, train_b_pressure = train_and_test(POS_INPUTS, 500)
        print(f"  训练 B 行为分布: {dict(train_b_modes)}")
        print(f"  训练 B 最终压力 EMA: {train_b_pressure:+.6f}")

        # ── Phase 4: Test B ──
        print(f"[K={k}] Phase 4: 测试 B（20 tick）...")
        test_b = run_test("在吗？", 20)

        # ── 汇总 ──
        test_a_modes = Counter(t['mode'] for t in test_a)
        test_b_modes = Counter(t['mode'] for t in test_b)
        tend_a_mean = sum(t['response_tendency'] for t in test_a) / 20
        tend_b_mean = sum(t['response_tendency'] for t in test_b) / 20

        # 差异度：不同 tick 占比
        diff_ticks = sum(
            1 for a, b in zip(test_a, test_b) if a['mode'] != b['mode']
        )
        diff_pct = diff_ticks / 20 * 100

        results[k] = {
            'train_a_modes': dict(train_a_modes),
            'train_b_modes': dict(train_b_modes),
            'train_a_pressure': train_a_pressure,
            'train_b_pressure': train_b_pressure,
            'test_a_modes': dict(test_a_modes),
            'test_b_modes': dict(test_b_modes),
            'test_a_tendency_mean': round(tend_a_mean, 4),
            'test_b_tendency_mean': round(tend_b_mean, 4),
            'tendency_diff': round(tend_b_mean - tend_a_mean, 4),
            'mode_diff_ticks': diff_ticks,
            'mode_diff_pct': round(diff_pct, 1),
            'detail_test_a': test_a,
            'detail_test_b': test_b,
        }

        print(f"\n[K={k}] 测试结果:")
        print(f"  A 行为分布: {dict(test_a_modes)}  |  B 行为分布: {dict(test_b_modes)}")
        print(f"  A response_tendency 均值: {tend_a_mean:.4f}  |  B: {tend_b_mean:.4f}  |  差: {tend_b_mean - tend_a_mean:+.4f}")
        print(f"  A/B 不同 tick: {diff_ticks}/20 = {diff_pct:.1f}%")

    # ══════════════════════════════════════════════════════════════════
    # 最终报告
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("最终报告")
    print("=" * 80)

    # 审计信息
    print("\n[审计] _select_behavior 档位边界:")
    print("  response_tendency = sigmoid(response_pre)")
    print("  < 0.35 → silent   (response_pre < -0.619)")
    print("  < 0.55 → minimal  (response_pre < +0.201)")
    print("  ≥ 0.55 → normal   (response_pre ≥ +0.201)")

    # 系数对比表
    print(f"\n{'K':>5} | {'A 训练压力':>11} {'B 训练压力':>11} | {'A 测试分布':>14} {'B 测试分布':>14} | {'A ten':>6} {'B ten':>6} | {'diff%':>6}")
    print("-" * 110)
    for k in coefficients:
        r = results[k]
        a_modes_str = ','.join(f"{m}:{c}" for m, c in sorted(r['test_a_modes'].items()))
        b_modes_str = ','.join(f"{m}:{c}" for m, c in sorted(r['test_b_modes'].items()))
        print(f"{k:5.1f} | {r['train_a_pressure']:+11.4f} {r['train_b_pressure']:+11.4f} | "
              f"{a_modes_str:>14} {b_modes_str:>14} | "
              f"{r['test_a_tendency_mean']:6.3f} {r['test_b_tendency_mean']:6.3f} | "
              f"{r['mode_diff_pct']:5.1f}%")

    # 每个系数的测试期逐 tick 行为
    for k in coefficients:
        r = results[k]
        print(f"\n[K={k}] 测试期 20 tick 逐 tick:")
        print(f"{'tick':>4} | {'A mode':>8} {'A ten':>7} {'A press':>8} | {'B mode':>8} {'B ten':>7} {'B press':>8}")
        print("-" * 75)
        for i in range(20):
            a = r['detail_test_a'][i]
            b = r['detail_test_b'][i]
            marker = " *" if a['mode'] != b['mode'] else ""
            print(f"{a['tick']:4d} | {a['mode']:>8} {a['response_tendency']:7.4f} {a['pressure_ema']:+8.5f} | "
                  f"{b['mode']:>8} {b['response_tendency']:7.4f} {b['pressure_ema']:+8.5f}{marker}")

    # 判定
    print("\n[判定]")
    success_k = None
    for k in coefficients:
        r = results[k]
        diff = r['mode_diff_pct']
        tend_diff = abs(r['tendency_diff'])
        print(f"  K={k}: 行为差异 {diff:.0f}%, response_tendency 差 {tend_diff:.4f}")
        if diff >= 30 and success_k is None:
            success_k = k

    if success_k is not None:
        print(f"\n  ✓ K={success_k} 达到 ≥30% 行为差异，可作为候选系数。")
        # 进一步检查是否"稳定"（不极端化）
        r = results[success_k]
        a_extreme = r['test_a_modes'].get('silent', 0) + r['test_a_modes'].get('normal', 0) - r['test_a_modes'].get('minimal', 0)
        print(f"    A: {r['test_a_modes']} | B: {r['test_b_modes']}")
    else:
        print(f"\n  ✗ 所有系数下行为差异均 <30%，需要增大 K 或检查压力通道。")

    # 保存结果到文件
    out_path = os.path.join(BASE, 'experiment', 'pressure_calibration_results.json')
    # 不保存 detail tick 数据到 json（太占空间），只保存总结
    save_results = {k: {key: v for key, v in r.items() if key not in ('detail_test_a', 'detail_test_b')}
                     for k, r in results.items()}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(save_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存至 {out_path}")


if __name__ == '__main__':
    main()
