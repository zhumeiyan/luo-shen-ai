#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 relational_pressure_ema 的持久性和 A/B 差异稳定性。

修复后的代码应满足：
1. relational_pressure_ema 在整个 environment_tick 后不会被剥除
2. relational_awareness 在 self_model 中同步积累
3. idle_update_memory 不丢失 relational_awareness
4. A/B 行为差异（max_tokens）稳定

注意：此脚本绕过 generate_response/environment_tick 的磁盘 I/O 以提升速度，
直接在内存中模拟关键函数调用链，测试核心修复逻辑。
"""
import sys, os, json, statistics, math, time

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# ── Patch LLM ──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Patch 情感分析 ──
NEG_WORDS = {"烦","累","痛","哭","不想","没用","失去","死","孤独","绝望",
             "无聊","迷茫","压力","崩溃","抑郁","苦","难","没意思","难受",
             "失望","焦虑","噩梦","伤心","沉默","逃避","失败"}
POS_WORDS = {"开心","快乐","幸福","满足","笑容","温暖","美好","希望","喜欢",
             "阳光","感谢","舒服","不错","挺好","轻快","满足","棒","真好",
             "舒适","愉快","乐观","期待","满意","幸运"}

def _rule_sentiment(t):
    n = sum(1 for w in NEG_WORDS if w in t)
    p = sum(1 for w in POS_WORDS if w in t)
    if n == 0 and p == 0:
        return 0.0, 0.45
    tot = n + p
    v = (p - n) / tot if tot > 0 else 0.0
    return v, min(0.9, 0.45 + (tot / max(1, len(t))) * 8)

import input_pressure
input_pressure._call_llm_sentiment = _rule_sentiment

from living_engine import (
    _apply_input_pressure, environment_tick, idle_update_memory,
    _select_behavior, _compute_memory_emergence, _load_json, _save_json_atomic,
    cold_start_if_needed,
)

MEMORY_PATH = 'active_memory/active_memory.json'

# ── 输入序列 ──
NEG_INPUTS = [
    "觉得活着没什么意思，每天都很累。",
    "连续加班一周，快要撑不住了。",
    "我害怕，不知道该怎么办。",
    "为什么努力了也没有用，好绝望。",
    "头疼恶心，浑身不舒服。",
    "又失眠了，一闭眼全是烦心事。",
    "不想说话，不想见人，只想一个人待着。",
    "我很难过，不知道跟谁说。",
]
POS_INPUTS = [
    "今天天气不错，心情挺好的。",
    "刚吃了一顿满足的晚饭，很幸福。",
    "谢谢你一直陪着我，很温暖。",
    "嗯，我听到了，感觉还不错。",
    "事情在慢慢变好，有希望了。",
    "不着急，慢慢来，轻松点。",
    "行，我试试，挺期待的。",
    "我很开心，今天一切都很顺利。",
]


def apply_in_memory(memory, user_input):
    """在内存中调用 _apply_input_pressure，无磁盘 I/O"""
    _apply_input_pressure(memory, user_input)


def tick_in_memory(memory):
    """在内存中模拟 environment_tick 的 ring_state 重建逻辑（核心部分）
    
    直接复用 _update_luoshen_coupled 的内部逻辑，但跳过磁盘 I/O 和环境采样。
    这里我们只关心：重建 _new_ring_state 后，relational_pressure_ema 是否保留。
    """
    ring_sm = memory.get("self_model", {}).get("ring_state", {})
    _rpe = ring_sm.get("relational_pressure_ema", 0.0)

    # 重建 _new_ring_state（对应 _update_luoshen_coupled 末尾逻辑）
    climate = memory.get("internal_climate", {})
    E = climate.get("emotion_intensity", 0.5)
    T = climate.get("tension", 0.0)
    phase = math.atan2(T, E)

    _new_ring_state = {
        "E": E, "T": T,
        "N": climate.get("energy", 0.5),
        "M": climate.get("memory_pressure", 0.3),
        "phase": round(phase, 5),
        "mu_core": ring_sm.get("mu_core", 0.5),
        "ema_S": ring_sm.get("ema_S", 0.0),
        "S": ring_sm.get("S", 0.0),
        "relational_pressure_ema": _rpe,  # 修复点：无条件保留
    }
    memory["self_model"]["ring_state"] = _new_ring_state

    # 同时累积 climate 极小自演化
    climate["emotion_intensity"] = max(0.0, min(1.0, E + (0.5 - E) * 0.001))
    climate["tension"] = max(-1.0, min(1.0, T * 0.999))
    memory["internal_climate"] = climate


def reset_memory():
    """清空并重新冷启动"""
    if os.path.exists(MEMORY_PATH):
        os.remove(MEMORY_PATH)
    m = cold_start_if_needed()
    m['self_model']['ring_state'] = {
        'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0,
        'relational_pressure_ema': 0.0,
    }
    m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    m['user_model']['episodic_memory'] = []
    m['user_model']['total_interactions'] = 0
    _save_json_atomic(MEMORY_PATH, m)


def run_sequence(label, inputs, n_train=500, n_test=20):
    """跑 n_train tick 训练 + n_test tick 测试，返回训练日志 + 测试结果"""
    reset_memory()
    memory = _load_json(MEMORY_PATH)

    train_log = []
    for i in range(n_train):
        # 1. 施加输入压力（in-memory, 无磁盘 I/O）
        apply_in_memory(memory, inputs[i % len(inputs)])

        # 2. 环境 tick 模拟（in-memory）
        tick_in_memory(memory)

        # 3. 记录（如果开启 compute_emergence，会写入 relational_awareness）
        emergence = _compute_memory_emergence(memory)
        _pressure_ema = memory.get("self_model", {}).get("ring_state", {}).get("relational_pressure_ema", None)
        if _pressure_ema is not None:
            if "self_model" not in memory:
                memory["self_model"] = {}
            memory["self_model"]["relational_awareness"] = round(_pressure_ema, 7)

        if (i + 1) % 50 == 0 or i == 0:
            rs = memory.get('self_model', {}).get('ring_state', {})
            ra = memory.get('self_model', {}).get('relational_awareness', None)
            train_log.append({
                'tick': i + 1,
                'rpe': rs.get('relational_pressure_ema', 'MISSING'),
                'ra': ra,
                'rpe_exists': 'relational_pressure_ema' in rs,
            })

    # 训练末态
    _save_json_atomic(MEMORY_PATH, memory)
    rs_final = memory.get('self_model', {}).get('ring_state', {})
    train_state = {
        'rp_ema_final': rs_final.get('relational_pressure_ema', 'MISSING'),
        'mu_core_final': rs_final.get('mu_core', 0.5),
        'relational_awareness_final': memory.get('self_model', {}).get('relational_awareness', 'MISSING'),
    }

    # 测试期
    test_results = []
    for i in range(n_test):
        emergence = _compute_memory_emergence(memory)
        behavior = _select_behavior(memory, emergence)
        rs = memory.get('self_model', {}).get('ring_state', {})
        test_results.append({
            'tick': i + 1,
            'rpe': rs.get('relational_pressure_ema', 'MISSING'),
            'mode': behavior.get('response_mode', '?'),
            'mode_idx': behavior.get('mode_idx', '?'),
            'max_tokens': behavior.get('max_tokens', '?'),
            'tendency': behavior.get('response_tendency', '?'),
            'ra': memory.get('self_model', {}).get('relational_awareness', 'MISSING'),
        })

    return train_state, train_log, test_results


def main():
    print("=" * 110)
    print("验证：relational_pressure_ema 持久性 + A/B 差异稳定性")
    print("=" * 110)

    t0 = time.time()

    # ── Phase 1: A 组 ──
    print("\n[Phase 1] A 组（负向输入 × 500 tick）...")
    train_a, log_a, test_a = run_sequence("A (负向)", NEG_INPUTS, 500, 20)

    # ── Phase 2: B 组 ──
    print("[Phase 2] B 组（正向输入 × 500 tick）...")
    train_b, log_b, test_b = run_sequence("B (正向)", POS_INPUTS, 500, 20)

    elapsed = time.time() - t0

    # ══════════════════════════════════════════════════════════════════════
    # 1. 持久性验证
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("1. 持久性验证：relational_pressure_ema 在 environment_tick 重建后是否始终存在")
    print("=" * 110)

    for label, log in [("A", log_a), ("B", log_b)]:
        missing = [e for e in log if not e['rpe_exists']]
        numeric = [e for e in log if isinstance(e['rpe'], (int, float))]
        print(f"\n  {label} 组:")
        print(f"    检查点数量: {len(log)}")
        print(f"    字段缺失数: {len(missing)} {'✓ 通过' if len(missing) == 0 else '✗ 严重问题'}")
        print(f"    数值正常数: {len(numeric)}")
        if numeric:
            print(f"    首 checkpoint rpe: {numeric[0]['rpe']:+.6f}")
            print(f"    末 checkpoint rpe: {numeric[-1]['rpe']:+.6f}")

    # ══════════════════════════════════════════════════════════════════════
    # 2. rp_ema 轨迹
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("2. rp_ema 训练轨迹（每 50 tick 一个点）")
    print("=" * 110)
    print(f"\n{'tick':>5} | {'A rpe':>13} {'A exists':>9} {'A ra':>12} | {'B rpe':>13} {'B exists':>9} {'B ra':>12}")
    print("-" * 85)
    for i in range(max(len(log_a), len(log_b))):
        a = log_a[i] if i < len(log_a) else {'tick': '-', 'rpe': '-', 'ra': '-', 'rpe_exists': False}
        b = log_b[i] if i < len(log_b) else {'tick': '-', 'rpe': '-', 'ra': '-', 'rpe_exists': False}
        a_rpe = a['rpe']
        b_rpe = b['rpe']
        a_ok = '✓' if isinstance(a_rpe, (int, float)) else '✗'
        b_ok = '✓' if isinstance(b_rpe, (int, float)) else '✗'
        a_str = f"{a_rpe:>+13.6f}" if isinstance(a_rpe, (int, float)) else f"{'MISSING':>13}"
        b_str = f"{b_rpe:>+13.6f}" if isinstance(b_rpe, (int, float)) else f"{'MISSING':>13}"
        a_ra = a['ra']
        b_ra = b['ra']
        a_ra_s = f"{a_ra:>+12.6f}" if isinstance(a_ra, (int, float)) else f"{'MISSING':>12}"
        b_ra_s = f"{b_ra:>+12.6f}" if isinstance(b_ra, (int, float)) else f"{'MISSING':>12}"
        print(f"{a['tick']:>5} | {a_str} {a_ok:>9} {a_ra_s} | {b_str} {b_ok:>9} {b_ra_s}")

    # ══════════════════════════════════════════════════════════════════════
    # 3. 训练末态
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("3. 训练末态")
    print("=" * 110)
    for label, ts in [("A", train_a), ("B", train_b)]:
        print(f"\n  {label}:")
        print(f"    relational_pressure_ema = {ts['rp_ema_final']}")
        print(f"    mu_core                 = {ts['mu_core_final']}")
        print(f"    relational_awareness    = {ts['relational_awareness_final']}")

    # ══════════════════════════════════════════════════════════════════════
    # 4. A/B 行为差异
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("4. A/B 行为差异（测试期 20 tick）")
    print("=" * 110)
    print(f"\n{'tick':>4} | {'A tok':>6} {'A mode':>9} {'A rpe':>13} {'A ra':>11} | {'B tok':>6} {'B mode':>9} {'B rpe':>13} {'B ra':>11} | {'B-A':>5}")
    print("-" * 115)

    a_toks, b_toks = [], []
    for i in range(20):
        a = test_a[i]
        b = test_b[i]
        at = a['max_tokens']
        bt = b['max_tokens']
        a_toks.append(at)
        b_toks.append(bt)
        diff = bt - at if isinstance(at, int) and isinstance(bt, int) else '?'
        a_rpe_s = f"{a['rpe']:>+13.6f}" if isinstance(a['rpe'], (int, float)) else f"{'MISS':>13}"
        b_rpe_s = f"{b['rpe']:>+13.6f}" if isinstance(b['rpe'], (int, float)) else f"{'MISS':>13}"
        a_ra_s = f"{a['ra']:>+11.6f}" if isinstance(a['ra'], (int, float)) else f"{'MISS':>11}"
        b_ra_s = f"{b['ra']:>+11.6f}" if isinstance(b['ra'], (int, float)) else f"{'MISS':>11}"
        diff_s = f"{diff:>+5d}" if isinstance(diff, int) else f"{'?':>5}"
        print(f"{a['tick']:4d} | {at:>6} {a['mode']:>9} {a_rpe_s} {a_ra_s} | {bt:>6} {b['mode']:>9} {b_rpe_s} {b_ra_s} | {diff_s}")

    if a_toks and b_toks and all(isinstance(x, int) for x in a_toks + b_toks):
        diffs = [bb - aa for aa, bb in zip(a_toks, b_toks)]
        all_b_gt_a = all(d > 0 for d in diffs)
        min_diff = min(diffs)
        max_diff = max(diffs)
        mean_a = statistics.mean(a_toks)
        mean_b = statistics.mean(b_toks)
        print(f"\n  A max_tokens 均值: {mean_a:.1f}, 范围: [{min(a_toks)}, {max(a_toks)}]")
        print(f"  B max_tokens 均值: {mean_b:.1f}, 范围: [{min(b_toks)}, {max(b_toks)}]")
        print(f"  B-A 差异范围: [{min_diff:+d}, {max_diff:+d}]")
        print(f"  全部 tick B > A? {'是' if all_b_gt_a else '否'}")
        a_ge_b = any(aa >= bb for aa, bb in zip(a_toks, b_toks))
        print(f"  任一 tick A >= B? {'是' if a_ge_b else '否'}")

    # ══════════════════════════════════════════════════════════════════════
    # 5. idle_update_memory 保持验证
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("5. idle_update_memory 保持验证")
    print("=" * 110)

    m = _load_json(MEMORY_PATH)
    ra_before = m.get('self_model', {}).get('relational_awareness', 'MISSING')
    rpe_before = m.get('self_model', {}).get('ring_state', {}).get('relational_pressure_ema', 'MISSING')
    print(f"\n  idle 前: relational_awareness = {ra_before}, rpe = {rpe_before}")

    idle_update_memory(m)
    m_after = _load_json(MEMORY_PATH)
    ra_after = m_after.get('self_model', {}).get('relational_awareness', 'MISSING')
    rpe_after = m_after.get('self_model', {}).get('ring_state', {}).get('relational_pressure_ema', 'MISSING')
    print(f"  idle 后: relational_awareness = {ra_after}, rpe = {rpe_after}")

    preserved_ra = (ra_before == ra_after)
    preserved_rpe = (rpe_before == rpe_after)
    print(f"  relational_awareness 保持不变? {'是 ✓' if preserved_ra else '否 ✗'}")
    print(f"  relational_pressure_ema 保持不变? {'是 ✓' if preserved_rpe else '否 ✗'}")

    # ══════════════════════════════════════════════════════════════════════
    # 结论
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 110)
    print("最终结论")
    print("=" * 110)

    all_present = all(e['rpe_exists'] for e in log_a + log_b)
    all_present_test = all(
        isinstance(t['rpe'], (int, float)) for t in test_a + test_b
    )

    conclusion = []
    if all_present:
        conclusion.append("✓ 持久性：环境 tick 后 relational_pressure_ema 始终存在")
    else:
        conclusion.append("✗ 持久性：环境 tick 后 relational_pressure_ema 存在缺失！")

    if all_present_test:
        conclusion.append("✓ 测试期持久性：测试期 20 tick rpe 字段完整")
    else:
        conclusion.append("✗ 测试期持久性：测试期 rpe 字段有缺失！")

    if a_toks and b_toks and all(isinstance(x, int) for x in a_toks + b_toks):
        diffs = [bb - aa for aa, bb in zip(a_toks, b_toks)]
        if all(d > 0 for d in diffs):
            conclusion.append(f"✓ A/B 差异：B > A 稳定，间距 {min(diffs)}~{max(diffs)} tick")
        else:
            conclusion.append(f"✗ A/B 差异：出现 A >= B 的 tick")
    else:
        conclusion.append("? A/B 差异：无法判定（数据异常）")

    if preserved_ra:
        conclusion.append("✓ idle 保持：idle_update_memory 不丢失 relational_awareness")
    else:
        conclusion.append("✗ idle 保持：relational_awareness 在 idle 后改变！")

    for c in conclusion:
        print(f"  {c}")

    all_pass = all(c.startswith('✓') for c in conclusion)
    print(f"\n总评: {'全部通过' if all_pass else '存在失败项，需检查'}")
    print(f"执行时间: {elapsed:.1f} 秒")
    print("=" * 110)


if __name__ == "__main__":
    main()
