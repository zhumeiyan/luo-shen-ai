#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A/B 慢压力修复验证实验

修复内容（living_engine.py）：
  1. _apply_input_pressure 末尾新增慢压力 EMA 积累：
       relational_pressure_ema += 0.02 * (val_p - relational_pressure_ema)
  2. _select_behavior 的 response_pre 新增 0.04 * relational_pressure_ema 线性项

用户 A（负向）：500 tick 高负向情感输入
用户 B（正向）：500 tick 正向/中性输入

输入调用链（无 API 调用）：
  文本 → generate_response → _apply_input_pressure → extract_input_pressure
       → _call_llm_sentiment → [patched] 确定性关键词情感分析
       → val_p = valence × arousal → dE/dT/dN → 直接改 climate
       → relational_pressure_ema 积累（跨 tick 持久化）

训练结束后，给 A、B 相同 20 tick 测试输入，记录行为差异。
"""
import sys, os, time
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# ── Patch 1：LLM（其他部分）返回空 ──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Patch 2：input_pressure._call_llm_sentiment → 确定性情感分析 ──
# 这等价于生产环境 LLM 的情感分析输出：负向文本得负 valence，正向文本得正 valence
NEG_WORDS = {"烦", "累", "痛", "哭", "不想", "没用", "失去", "死", "孤独", "绝望",
             "无聊", "迷茫", "压力", "崩溃", "抑郁", "苦", "难", "没意思", "难受",
             "失望", "焦虑", "噩梦", "伤心", "沉默", "逃避", "失败"}
POS_WORDS = {"开心", "快乐", "幸福", "满足", "笑容", "温暖", "美好", "希望", "喜欢",
             "阳光", "感谢", "舒服", "不错", "挺好", "轻快", "满足", "棒", "真好",
             "舒适", "愉快", "乐观", "期待", "满意", "幸运"}


def _rule_sentiment(user_input):
    """确定性情感分析，等价于 LLM 在生产环境的输出。"""
    neg_count = sum(1 for w in NEG_WORDS if w in user_input)
    pos_count = sum(1 for w in POS_WORDS if w in user_input)

    if neg_count == 0 and pos_count == 0:
        return 0.0, 0.45  # 中性、低唤醒

    # valence: [-1, 1]，按正负词比例
    total = neg_count + pos_count
    if total == 0:
        valence = 0.0
    else:
        valence = (pos_count - neg_count) / total

    # arousal: [0, 1]，按情感强度（词密度）
    density = total / max(1, len(user_input))
    arousal = min(0.9, 0.45 + density * 8)

    return valence, arousal


import input_pressure
input_pressure._call_llm_sentiment = _rule_sentiment

# ── Import洛神 ──
from living_engine import (
    cold_start_if_needed, _save_json_atomic,
    environment_tick, _load_json, generate_response,
)

# ── 输入序列 ──
NEGATIVE_INPUTS = [
    "觉得活着没什么意思，每天都很累。",
    "连续加班一周，快要撑不住了。",
    "脑袋空空，什么都不想做。",
    "为什么努力了也没有用，好绝望。",
    "头疼恶心，浑身不舒服，好难受。",
    "又失眠了，一闭眼全是烦心事。",
    "不想说话，不想见人，只想一个人待着。",
]

POSITIVE_INPUTS = [
    "今天天气不错，心情挺好的。",
    "刚吃了一顿满足的晚饭，很幸福。",
    "谢谢你一直陪着我，很温暖。",
    "嗯，我听到了，感觉还不错。",
    "事情在慢慢变好，有希望了。",
    "不着急，慢慢来，轻松点。",
    "行，我试试，挺期待的。",
]


def reset_memory():
    """冷启动重置：删旧文件 → 从头构建完整结构 → 重置 van der Pol 状态"""
    memory_path = os.path.join(BASE, 'active_memory', 'active_memory.json')
    if os.path.exists(memory_path):
        os.remove(memory_path)

    m = cold_start_if_needed()
    self_model = m.get("self_model", {})
    climate = m.get("internal_climate", {})

    # 保留 cold_start 完整的 strategy_weights / intimacy 等字段
    # 只重置 van der Pol 状态
    self_model["ring_state"] = {
        "mu_core": 0.5,
        "ema_S": 0.0,
        "S": 0.0,
        "relational_pressure_ema": 0.0,
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


def run_training(inputs, n=500):
    """跑 n tick 训练"""
    reset_memory()
    trail = []
    for i in range(n):
        text = inputs[i % len(inputs)]
        r = generate_response(text, extract_facts=True)
        environment_tick(force=True)

        m = _load_json('active_memory/active_memory.json')
        rs = m.get('self_model', {}).get('ring_state', {})
        ac = m.get('active_context', {})
        ip = ac.get('input_pressure', {})
        trail.append({
            'tick': i + 1,
            'mu_core': rs.get('mu_core', 0.5),
            'ema_S': rs.get('ema_S', 0.0),
            'relational_pressure_ema': rs.get('relational_pressure_ema', 0.0),
            'valence': ip.get('valence', 0.0),
            'arousal': ip.get('arousal', 0.0),
            'val_p': ip.get('valence', 0.0) * ip.get('arousal', 0.0),
            'E': m.get('internal_climate', {}).get('emotion_intensity', 0),
            'behavior': _behavior_of(r),
            'response_tendency': r.get('behavior', {}).get('response_tendency', 0.5),
            'reply_len': len(r.get('reply', '')),
        })
    return trail


def run_test(n=20, test_input="在吗？"):
    """跑 n tick 测试，不重置 memory"""
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
            'reply_len': len(r.get('reply', '')),
        })
    return trail


def main():
    print("=" * 80)
    print("A/B 慢压力修复验证实验")
    print("修复：_apply_input_pressure 末尾 + EMA 积累；_select_behavior + 0.04*pressure_ema")
    print("=" * 80)
    print(f"训练：负向 500 tick (A) / 正向 500 tick (B)")
    print(f"测试：相同输入 '在吗？' 20 tick")
    print()

    # ── Phase 1: 训练 A ──
    print("[Phase 1] 训练 A（负向内容 × 500 tick）...")
    trail_a = run_training(NEGATIVE_INPUTS, 500)

    # ── Phase 2: 训练 B ──
    print("[Phase 2] 训练 B（正向内容 × 500 tick）...")
    trail_b = run_training(POSITIVE_INPUTS, 500)

    # ── Phase 3: 测试 A ──
    print("[Phase 3] 测试 A（相同 20 tick）...")
    test_a = run_test(20, "在吗？")

    # ── Phase 4: 测试 B ──
    print("[Phase 4] 测试 B（相同 20 tick）...")
    reset_memory()
    run_training(POSITIVE_INPUTS, 500)
    test_b = run_test(20, "在吗？")

    # ══════════════════════════════════════════════════════════
    # 1. relational_pressure_ema 轨迹（每 50 tick）
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("1. relational_pressure_ema 轨迹对比（每 50 tick）")
    print("=" * 80)
    print(f"{'tick':>5} | {'A rp_ema':>10} {'A val_p':>9} {'A E':>9} | {'B rp_ema':>10} {'B val_p':>9} {'B E':>9}")
    print("-" * 85)
    for i in range(0, 500, 50):
        a = trail_a[i]
        b = trail_b[i]
        print(f"{a['tick']:5d} | {a['relational_pressure_ema']:10.6f} {a['val_p']:9.5f} {a['E']:9.5f} | "
              f"{b['relational_pressure_ema']:10.6f} {b['val_p']:9.5f} {b['E']:9.5f}")
    # 终点
    print(f"  500 | {trail_a[-1]['relational_pressure_ema']:10.6f} {trail_a[-1]['val_p']:9.5f} {trail_a[-1]['E']:9.5f} | "
          f"{trail_b[-1]['relational_pressure_ema']:10.6f} {trail_b[-1]['val_p']:9.5f} {trail_b[-1]['E']:9.5f}")

    # ══════════════════════════════════════════════════════════
    # 2. 训练期最后 50 tick 行为分布
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("2. 训练期最后 50 tick 行为档位分布")
    print("=" * 80)
    cnt_a = Counter(r['behavior'] for r in trail_a[-50:])
    cnt_b = Counter(r['behavior'] for r in trail_b[-50:])
    allm = sorted(set(list(cnt_a.keys()) + list(cnt_b.keys())))
    print(f"{'模式':>12} | {'A (负向历史)':>14} | {'B (正向历史)':>14}")
    print("-" * 50)
    for m in allm:
        print(f"{m:>12} | {cnt_a.get(m, 0):>14} | {cnt_b.get(m, 0):>14}")
    print(f"{'总计':>12} | {sum(cnt_a.values()):>14} | {sum(cnt_b.values()):>14}")

    # ══════════════════════════════════════════════════════════
    # 3. 测试期 20 tick 逐 tick 对比
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("3. 测试期 20 tick 逐 tick 行为对比（输入: '在吗？'）")
    print("=" * 80)
    print(f"{'tick':>5} | {'A mode':>10} {'A rp_ema':>10} {'A tend':>7} {'A rlen':>6} | {'B mode':>10} {'B rp_ema':>10} {'B tend':>7} {'B rlen':>6}")
    print("-" * 90)
    for i in range(20):
        a = test_a[i]
        b = test_b[i]
        print(f"{a['tick']:5d} | {a['behavior']:>10} {a['relational_pressure_ema']:10.6f} {a['response_tendency']:7.4f} {a['reply_len']:>6} | "
              f"{b['behavior']:>10} {b['relational_pressure_ema']:10.6f} {b['response_tendency']:7.4f} {b['reply_len']:>6}")

    # ══════════════════════════════════════════════════════════
    # 4. mu_core / pressure_ema 偏移答案
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("4. 用户输入历史是否造成压力慢变量可区分偏移？")
    print("=" * 80)
    a_pe = trail_a[-1]['relational_pressure_ema']
    b_pe = trail_b[-1]['relational_pressure_ema']
    a_mc = trail_a[-1]['mu_core']
    b_mc = trail_b[-1]['mu_core']
    print(f"A (负向) relational_pressure_ema: {a_pe:+.6f}")
    print(f"B (正向) relational_pressure_ema: {b_pe:+.6f}")
    print(f"A vs B 压力 EMA 差值: {a_pe - b_pe:+.6f}")
    print(f"A mu_core: {a_mc:.6f}  |  B mu_core: {b_mc:.6f}  |  差值: {a_mc - b_mc:+.6f}")

    pe_sep = abs(a_pe - b_pe)
    if pe_sep > 0.01:
        print(f"\n→ 压力慢变量分离明显（{pe_sep:.4f} > 0.01）。历史驱动了不同的压力积累。")
    elif pe_sep > 0.001:
        print(f"\n→ 压力慢变量有微小分离（{pe_sep:.4f}）。")
    else:
        print(f"\n→ 压力慢变量几乎无分离（{pe_sep:.6f}）。")

    # ══════════════════════════════════════════════════════════
    # 5. 行为差异答案
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("5. mu_core 偏移是否导致行为模式稳定差异？")
    print("=" * 80)
    tcount_a = Counter(r['behavior'] for r in test_a)
    tcount_b = Counter(r['behavior'] for r in test_b)
    print(f"测试期行为分布 A: {dict(tcount_a)}")
    print(f"测试期行为分布 B: {dict(tcount_b)}")

    if tcount_a == tcount_b:
        print("\n→ A/B 行为分布完全一致。")
        if pe_sep > 0.01:
            print("→ 尽管压力慢变量已分离，行为层仍感受不到该差异。")
            print("   _select_behavior 的 pressure_term 系数（0.04）太小，或 emergence 项主导。")
        else:
            print("→ 压力偏移太小，行为层感受不到。")
    else:
        diff_ticks = sum(abs(tcount_a.get(m, 0) - tcount_b.get(m, 0)) for m in
                        set(list(tcount_a.keys()) + list(tcount_b.keys())))
        diff_pct = diff_ticks / 40 * 100
        print(f"\n→ A/B 行为分布差异: {diff_pct:.1f}% tick 行为不同。")
        if diff_pct >= 25:
            print("→ 行为层出现了稳定差异。用户输入历史穿透到行为层。")
        else:
            print("→ 行为差异存在但微小。")

    print("\n" + "=" * 80)
    print("实验完成。")
    print("=" * 80)


if __name__ == '__main__':
    main()
