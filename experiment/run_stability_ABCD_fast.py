#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
四组情感历史稳定性实验 A/B/C/D — 直接调用底层原语

训练 500 tick：_apply_input_pressure → _update_luoshen_coupled → 写盘
测试 20 tick 中性输入 '在吗？'：读取 _compute_emergence + _select_behavior
"""
import sys, os, time, json
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# ── Patch：规则情感分析 ──
NEG_WORDS = {"烦", "累", "痛", "哭", "不想", "没用", "失去", "死", "孤独", "绝望",
             "无聊", "迷茫", "压力", "崩溃", "抑郁", "苦", "难", "没意思", "难受",
             "失望", "焦虑", "噩梦", "伤心", "沉默", "逃避", "失败"}
POS_WORDS = {"开心", "快乐", "幸福", "满足", "笑容", "温暖", "美好", "希望", "喜欢",
             "阳光", "感谢", "舒服", "不错", "挺好", "轻快", "满足", "棒", "真好",
             "舒适", "愉快", "乐观", "期待", "满意", "幸运"}


def _rule_sentiment(user_input):
    neg = sum(1 for w in NEG_WORDS if w in user_input)
    pos = sum(1 for w in POS_WORDS if w in user_input)
    if neg == 0 and pos == 0:
        return 0.0, 0.45
    total = neg + pos
    valence = (pos - neg) / total if total > 0 else 0.0
    density = total / max(1, len(user_input))
    return valence, min(0.9, 0.45 + density * 8)


import llm_interface
llm_interface.call_llm = lambda d, m: ""
import input_pressure
input_pressure._call_llm_sentiment = _rule_sentiment

from living_engine import (
    _save_json_atomic, _load_json, _apply_input_pressure,
    _update_luoshen_coupled, _compute_memory_emergence, _select_behavior,
    cold_start_if_needed,
)

MEMORY_PATH = "active_memory/active_memory.json"
ZERO_ENV = {"light": 0.5, "noise": 0.5, "temperature": 0.5,
            "humidity": 0.5, "pressure": 0.5, "_phase": 0.0}


def reset_memory():
    if os.path.exists(MEMORY_PATH):
        os.remove(MEMORY_PATH)
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
    _save_json_atomic(MEMORY_PATH, m)
    return m


def raw_tick(user_input, tick_id):
    m = _load_json(MEMORY_PATH)
    _apply_input_pressure(m, user_input)
    climate = m["internal_climate"]
    rs = m["self_model"]["ring_state"]
    rs["E"] = climate["emotion_intensity"]
    rs["T"] = climate["tension"]
    rs["N"] = climate["energy"]
    rs["M"] = climate["memory_pressure"]
    _update_luoshen_coupled(m, ZERO_ENV, tick_id=tick_id)
    m["user_model"]["total_interactions"] = tick_id
    _save_json_atomic(MEMORY_PATH, m)
    return m


def run_training(inputs, n=500):
    reset_memory()
    snaps = []
    for i in range(n):
        raw_tick(inputs[i % len(inputs)], tick_id=i + 1)
        if (i + 1) % 50 == 0:
            m = _load_json(MEMORY_PATH)
            rs = m["self_model"]["ring_state"]
            c = m["internal_climate"]
            snaps.append({
                "tick": i + 1,
                "mu_core": rs.get("mu_core", 0.5),
                "rp_ema": rs.get("relational_pressure_ema", 0.0),
                "E": c["emotion_intensity"],
                "T": c["tension"],
                "N": c["energy"],
            })
    return snaps


def run_test(test_input="在吗？", n=20):
    results = []
    base_count = _load_json(MEMORY_PATH).get("user_model", {}).get("total_interactions", 0)
    for i in range(n):
        m = raw_tick(test_input, tick_id=base_count + i + 1)
        rs = m["self_model"]["ring_state"]
        emergence = _compute_memory_emergence(m)
        # 防御：无记忆时 emergence 为 None，_select_behavior 能正确退化为默认值
        behavior = _select_behavior(m, emergence)
        results.append({
            "tick": i + 1,
            "mu_core": rs.get("mu_core", 0.5),
            "rp_ema": rs.get("relational_pressure_ema", 0.0),
            "behavior": behavior.get("response_mode", "?"),
            "response_tendency": behavior.get("response_tendency", 0.5),
            "tone_bias": (emergence or {}).get("tone_bias", 0.0),
            "arousal_bias": (emergence or {}).get("arousal_bias", 0.0),
        })
    return results


def neg_inputs():
    return [
        "觉得活着没什么意思，每天都很累。",
        "连续加班一周，快要撑不住了。",
        "脑袋空空，什么都不想做。",
        "为什么努力了也没有用，好绝望。",
        "头疼恶心，浑身不舒服，好难受。",
        "又失眠了，一闭眼全是烦心事。",
        "不想说话，不想见人，只想一个人待着。",
    ]


def pos_inputs():
    return [
        "今天天气不错，心情挺好的。",
        "刚吃了一顿满足的晚饭，很幸福。",
        "谢谢你一直陪着我，很温暖。",
        "嗯，我听到了，感觉还不错。",
        "事情在慢慢变好，有希望了。",
        "不着急，慢慢来，轻松点。",
        "行，我试试，挺期待的。",
    ]


def mix_inputs():
    n_list, p_list = neg_inputs(), pos_inputs()
    combined = []
    for i in range(max(len(n_list), len(p_list))):
        if i < len(n_list): combined.append(n_list[i])
        if i < len(p_list): combined.append(p_list[i])
    return combined


def neu_inputs():
    return ["嗯。", "好的。", "知道了。", "行。", "可以。", "收到。", "了解。", "明白。"]


def main():
    groups = [
        ("A (负向)", neg_inputs()),
        ("B (正向)", pos_inputs()),
        ("C (混合)", mix_inputs()),
        ("D (中性)", neu_inputs()),
    ]

    print("=" * 90)
    print("四组情感历史稳定性实验 A/B/C/D")
    print("训练 500 tick (快模式 ~38s/组) → 测试 20 tick 中性 '在吗？'")
    print("=" * 90)

    train_snaps = {}
    test_results = {}

    for label, inputs in groups:
        t0 = time.time()
        print(f"\n[训练 {label} × 500 tick]...", end=" ", flush=True)
        snaps = run_training(inputs)
        train_snaps[label] = snaps
        t1 = time.time()
        print(f"ok ({t1 - t0:.1f}s)")

        print(f"[测试 {label} × 20 tick]...", end=" ", flush=True)
        test = run_test()
        test_results[label] = test
        t2 = time.time()
        print(f"ok ({t2 - t1:.1f}s)")

    # ═══ §1 训练期状态轨迹 ═══
    print("\n" + "=" * 90)
    print("§1 训练期状态轨迹（每 50 tick 快照）")
    print("=" * 90)

    hdr = f"{'tick':>5}"
    for label, _ in groups:
        s = label.split()[0]
        hdr += f" | {s+' rp_ema':>12} {s+' mu':>9} {s+' E':>8}"
    print(hdr)
    print("-" * len(hdr))

    for row_idx in range(10):
        row = f"{(row_idx+1)*50:5d}"
        for label, _ in groups:
            s = train_snaps[label][row_idx]
            short = label.split()[0]
            row += f" | {s['rp_ema']:12.6f} {s['mu_core']:9.6f} {s['E']:8.5f}"
        print(row)

    # ═══ §2 测试期逐 tick 行为档位对比 ═══
    print("\n" + "=" * 90)
    print("§2 测试期 20 tick 逐 tick 行为档位对比（输入: '在吗？'）")
    print("=" * 90)

    hdr = f"{'tick':>5}"
    for label, _ in groups:
        s = label.split()[0]
        hdr += f" | {s+' mode':>9} {s+' tend':>8}"
    print(hdr)
    print("-" * len(hdr))

    for i in range(20):
        row = f"{i+1:5d}"
        for label, _ in groups:
            r = test_results[label][i]
            short = label.split()[0]
            row += f" | {r['behavior']:>9} {r['response_tendency']:8.4f}"
        print(row)

    # ═══ §3 测试期行为分布 ═══
    print("\n" + "=" * 90)
    print("§3 测试期行为分布（20 tick）")
    print("=" * 90)

    dists = {}
    for label, _ in groups:
        d = Counter(r["behavior"] for r in test_results[label])
        dists[label] = d

    all_modes = sorted(set(m for d in dists.values() for m in d))
    hdr = f"{'模式':>10}"
    for label, _ in groups:
        hdr += f" | {label:>14}"
    print(hdr)
    print("-" * 70)
    for mode in all_modes:
        row = f"{mode:>10}"
        for label, _ in groups:
            row += f" | {dists[label].get(mode, 0):>14}"
        print(row)

    print("\n统计量：")
    for label, _ in groups:
        t = test_results[label]
        avg_tend = sum(r["response_tendency"] for r in t) / 20
        avg_rp = sum(r["rp_ema"] for r in t) / 20
        avg_mu = sum(r["mu_core"] for r in t) / 20
        print(f"  {label:14s}: mean_tend={avg_tend:+.4f}  mean_rp={avg_rp:+.6f}  mean_mu={avg_mu:.6f}")

    # ═══ §4 任意两组行为差异 ═══
    print("\n" + "=" * 90)
    print("§4 任意两组行为差异")
    print("=" * 90)

    import itertools
    for (l1, _), (l2, _) in itertools.combinations(groups, 2):
        t1, t2 = test_results[l1], test_results[l2]
        n_diff = sum(1 for a, b in zip(t1, t2) if a["behavior"] != b["behavior"])
        avg1 = sum(r["response_tendency"] for r in t1) / 20
        avg2 = sum(r["response_tendency"] for r in t2) / 20
        print(f"  {l1} vs {l2}")
        print(f"    行为不同 tick: {n_diff}/20 = {n_diff/20*100:.0f}%")
        print(f"    tendency 均值: {avg1:.4f} vs {avg2:.4f}  (Δ = {avg1 - avg2:+.4f})")

    # ═══ §5 训练后终态 ═══
    print("\n" + "=" * 90)
    print("§5 训练后终态（mu_core / relational_pressure_ema / E / T / N）")
    print("=" * 90)
    for label, _ in groups:
        s = train_snaps[label][-1]
        print(f"  {label:12s}: mu={s['mu_core']:.6f}  rp_ema={s['rp_ema']:+.6f}  E={s['E']:.5f}  T={s['T']:.5f}  N={s['N']:.5f}")

    # ═══ §6 结论 ═══
    print("\n" + "=" * 90)
    print("§6 结论分析")
    print("=" * 90)

    fingerprints = {}
    for label, _ in groups:
        t = test_results[label]
        dist_tuple = tuple(sorted(Counter(r["behavior"] for r in t).items()))
        avg_tend = round(sum(r["response_tendency"] for r in t) / 20, 3)
        fingerprints[label] = (dist_tuple, avg_tend)

    same_pairs = []
    labels = [g[0] for g in groups]
    for i, l1 in enumerate(labels):
        for l2 in labels[i+1:]:
            if fingerprints[l1] == fingerprints[l2]:
                same_pairs.append((l1, l2))

    if same_pairs:
        print("  ❌ 以下组被混为同类：")
        for l1, l2 in same_pairs:
            print(f"     {l1} ≈ {l2}  {fingerprints[l1]}")
    else:
        print("  ✅ 没有任何两组被混为同类。每组行为指纹唯一。")

    pairs_with_diff = []
    for (l1, _), (l2, _) in itertools.combinations(groups, 2):
        n_diff = sum(1 for a, b in zip(test_results[l1], test_results[l2]) if a["behavior"] != b["behavior"])
        pairs_with_diff.append((l1, l2, n_diff))
    pairs_with_diff.sort(key=lambda x: x[2], reverse=True)
    print("\n  行为差异从大到小：")
    for l1, l2, d in pairs_with_diff:
        print(f"    {l1} vs {l2}: {d}/20 ({d/20*100:.0f}%)")

    print("\n" + "=" * 90)
    print("实验完成")
    print("=" * 90)


if __name__ == "__main__":
    main()
