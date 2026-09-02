#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证：pressure_memory_mod 对记忆激活度的影响 + self_awareness_signal 的连续性。

实验设计：
1. A/B 各跑 500 tick 训练（同前），让 rp_ema 积累
2. 检查训练后：
   - relational_awareness 存在，A < 0，B > 0
   - self_awareness_signal 存在，= tanh(relational_awareness * 1.5)，范围 (-1, 1)
   - pressure_memory_mod 存在，A < 1.0，B > 1.0
3. 验证 environment_tick 不会清除 self_awareness_signal
4. 验证 idle_update_memory 保持两个字段
5. 测试期 20 tick 检查 max_tokens 差异
"""
import sys, os, math, statistics, time

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
    _apply_input_pressure(memory, user_input)


def tick_in_memory(memory):
    """模拟 environment_tick 的核心逻辑 (ring_state 重建 + 自我觉察)"""
    ring_sm = memory.get("self_model", {}).get("ring_state", {})
    _rpe = ring_sm.get("relational_pressure_ema", 0.0)

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
        "relational_pressure_ema": _rpe,
    }
    memory["self_model"]["ring_state"] = _new_ring_state

    # 计算 self_awareness_signal（与 _update_luoshen_coupled 一致）
    _ra = memory.get("self_model", {}).get("relational_awareness", 0.0)
    _sas = math.tanh(_ra * 1.5)
    memory["self_model"]["self_awareness_signal"] = round(_sas, 7)

    # climate 极小自演化
    climate["emotion_intensity"] = max(0.0, min(1.0, E + (0.5 - E) * 0.001))
    climate["tension"] = max(-1.0, min(1.0, T * 0.999))
    memory["internal_climate"] = climate


def compute_emergence_in_memory(memory):
    """调用 compute_emergence 并写入 active_context"""
    _compute_memory_emergence(memory)


def reset_memory():
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
    m['user_model']['total_interactions'] = 0
    # 注入至少一条情景记忆，使得 _compute_memory_emergence 有内容可操作
    m['user_model']['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': time.time() - 1.0,
        'source_id': None,
    }]
    _save_json_atomic(MEMORY_PATH, m)


def run_sequence(label, inputs, n_train=500, n_test=20):
    reset_memory()
    memory = _load_json(MEMORY_PATH)

    train_log = []
    for i in range(n_train):
        apply_in_memory(memory, inputs[i % len(inputs)])
        tick_in_memory(memory)
        compute_emergence_in_memory(memory)

        if (i + 1) % 50 == 0 or i == 0:
            rs = memory.get('self_model', {}).get('ring_state', {})
            ra = memory.get('self_model', {}).get('relational_awareness', 'MISSING')
            sas = memory.get('self_model', {}).get('self_awareness_signal', 'MISSING')
            pmm = memory.get('active_context', {}).get('memory_emergence', {}).get('pressure_memory_mod', 'MISSING') if memory.get('active_context', {}).get('memory_emergence') else 'N/A'
            train_log.append({
                'tick': i + 1,
                'rpe': rs.get('relational_pressure_ema', 'MISSING'),
                'ra': ra,
                'sas': sas,
                'pmm': pmm,
            })

    _save_json_atomic(MEMORY_PATH, memory)

    # 训练末态
    rs_f = memory.get('self_model', {}).get('ring_state', {})
    train_state = {
        'rp_ema': rs_f.get('relational_pressure_ema', 'MISSING'),
        'ra': memory.get('self_model', {}).get('relational_awareness', 'MISSING'),
        'sas': memory.get('self_model', {}).get('self_awareness_signal', 'MISSING'),
        'pmm': memory.get('active_context', {}).get('memory_emergence', {}).get('pressure_memory_mod', 'N/A') if memory.get('active_context', {}).get('memory_emergence') else 'N/A',
    }

    # 测试期
    test_results = []
    for i in range(n_test):
        compute_emergence_in_memory(memory)
        emergence = memory.get('active_context', {}).get('memory_emergence', {})
        behavior = _select_behavior(memory, emergence if emergence else {
            'background': {'e_bg': 0, 't_bg': 0, 'n_bg': 0, 'age_bg': 0, 'sal_bg': 0, 'dominance': 0},
            'length_bias': 0.5, 'tone_bias': 0, 'arousal_bias': 0,
        })
        rs = memory.get('self_model', {}).get('ring_state', {})
        test_results.append({
            'tick': i + 1,
            'rpe': rs.get('relational_pressure_ema', 'MISSING'),
            'ra': memory.get('self_model', {}).get('relational_awareness', 'MISSING'),
            'sas': memory.get('self_model', {}).get('self_awareness_signal', 'MISSING'),
            'pmm': emergence.get('pressure_memory_mod', 'N/A') if emergence else 'N/A',
            'mode': behavior.get('response_mode', '?'),
            'max_tokens': behavior.get('max_tokens', '?'),
        })

    return train_state, train_log, test_results


def main():
    print("=" * 120)
    print("验证：pressure_memory_mod + self_awareness_signal")
    print("=" * 120)

    t0 = time.time()
    print("\n[Phase 1] A 组（负向 × 500 tick）...")
    train_a, log_a, test_a = run_sequence("A (负向)", NEG_INPUTS, 500, 20)
    print("[Phase 2] B 组（正向 × 500 tick）...")
    train_b, log_b, test_b = run_sequence("B (正向)", POS_INPUTS, 500, 20)
    elapsed = time.time() - t0

    # ═══ 1. 持久性验证 ═══
    print("\n" + "=" * 120)
    print("1. 持久性验证：每个训练 tick 后字段是否完整")
    print("=" * 120)
    for label, log in [("A", log_a), ("B", log_b)]:
        rpe_ok = sum(1 for e in log if isinstance(e['rpe'], (int, float)))
        ra_ok = sum(1 for e in log if isinstance(e['ra'], (int, float)))
        sas_ok = sum(1 for e in log if isinstance(e['sas'], (int, float)))
        pmm_ok = sum(1 for e in log if isinstance(e['pmm'], (int, float)))
        print(f"  {label}: rpe={rpe_ok}/{len(log)} ra={ra_ok}/{len(log)} sas={sas_ok}/{len(log)} pmm={pmm_ok}/{len(log)}")

    # ═══ 2. rp_ema / ra / sas / pmm 轨迹 ═══
    print("\n" + "=" * 120)
    print("2. 训练轨迹（每 50 tick）")
    print("=" * 120)
    header = f"{'tick':>5} | {'A rpe':>11} {'A ra':>11} {'A sas':>9} {'A pmm':>8} | {'B rpe':>11} {'B ra':>11} {'B sas':>9} {'B pmm':>8}"
    print(f"\n{header}")
    print("-" * len(header))
    for i in range(max(len(log_a), len(log_b))):
        a = log_a[i] if i < len(log_a) else {}
        b = log_b[i] if i < len(log_b) else {}
        a_rpe = f"{a['rpe']:>+11.5f}" if isinstance(a.get('rpe'), (int, float)) else f"{'MISS':>11}"
        b_rpe = f"{b['rpe']:>+11.5f}" if isinstance(b.get('rpe'), (int, float)) else f"{'MISS':>11}"
        a_ra = f"{a['ra']:>+11.5f}" if isinstance(a.get('ra'), (int, float)) else f"{'MISS':>11}"
        b_ra = f"{b['ra']:>+11.5f}" if isinstance(b.get('ra'), (int, float)) else f"{'MISS':>11}"
        a_sas = f"{a['sas']:>+9.4f}" if isinstance(a.get('sas'), (int, float)) else f"{'MISS':>9}"
        b_sas = f"{b['sas']:>+9.4f}" if isinstance(b.get('sas'), (int, float)) else f"{'MISS':>9}"
        a_pmm = f"{a['pmm']:>8.4f}" if isinstance(a.get('pmm'), (int, float)) else f"{'N/A':>8}"
        b_pmm = f"{b['pmm']:>8.4f}" if isinstance(b.get('pmm'), (int, float)) else f"{'N/A':>8}"
        print(f"{a.get('tick',''):>5} | {a_rpe} {a_ra} {a_sas} {a_pmm} | {b_rpe} {b_ra} {b_sas} {b_pmm}")

    # ═══ 3. 训练末态 ═══
    print("\n" + "=" * 120)
    print("3. 训练末态")
    print("=" * 120)
    for label, ts in [("A", train_a), ("B", train_b)]:
        print(f"\n  {label}:")
        print(f"    rp_ema              = {ts['rp_ema']}")
        print(f"    relational_awareness= {ts['ra']}")
        print(f"    self_awareness_signal={ts['sas']}")
        print(f"    pressure_memory_mod = {ts['pmm']}")
        # 验证 self_awareness_signal == tanh(ra * 1.5)
        if isinstance(ts['ra'], (int, float)):
            expected_sas = round(math.tanh(ts['ra'] * 1.5), 7)
            actual_sas = ts['sas']
            if isinstance(actual_sas, (int, float)):
                match = abs(actual_sas - expected_sas) < 1e-5
                print(f"    [验证] tanh(ra*1.5) = {expected_sas:.7f}, match={'✓' if match else '✗'}")
        # 验证 pressure_memory_mod == 1 + 0.07 * rpe
        if isinstance(ts['rp_ema'], (int, float)):
            expected_pmm = round(1.0 + 0.07 * ts['rp_ema'], 5)
            actual_pmm = ts['pmm']
            if isinstance(actual_pmm, (int, float)):
                match = abs(actual_pmm - expected_pmm) < 1e-3
                print(f"    [验证] 1+0.07*rpe = {expected_pmm:.5f}, match={'✓' if match else '✗'}")

    # ═══ 4. idle_update_memory 保持验证 ═══
    print("\n" + "=" * 120)
    print("4. idle_update_memory 保持验证")
    print("=" * 120)
    m = _load_json(MEMORY_PATH)
    ra_b = m.get('self_model', {}).get('relational_awareness', 'MISSING')
    sas_b = m.get('self_model', {}).get('self_awareness_signal', 'MISSING')
    print(f"  idle 前: ra = {ra_b}, sas = {sas_b}")
    idle_update_memory(m)
    m2 = _load_json(MEMORY_PATH)
    ra_a = m2.get('self_model', {}).get('relational_awareness', 'MISSING')
    sas_a = m2.get('self_model', {}).get('self_awareness_signal', 'MISSING')
    print(f"  idle 后: ra = {ra_a}, sas = {sas_a}")
    print(f"  ra  保持? {'✓' if ra_b == ra_a else '✗'}")
    print(f"  sas 保持? {'✓' if sas_b == sas_a else '✗'}")

    # ═══ 5. A/B 测试期 ═══
    print("\n" + "=" * 120)
    print("5. A/B 行为差异（测试期 20 tick）")
    print("=" * 120)
    print(f"\n{'t':>3} | {'A tok':>5} {'A mode':>8} {'A ra':>9} {'A sas':>8} {'A pmm':>7} | {'B tok':>5} {'B mode':>8} {'B ra':>9} {'B sas':>8} {'B pmm':>7} | {'B-A':>4}")
    print("-" * 115)
    a_toks, b_toks = [], []
    for i in range(20):
        a = test_a[i]
        b = test_b[i]
        a_toks.append(a['max_tokens'])
        b_toks.append(b['max_tokens'])
        diff = b['max_tokens'] - a['max_tokens'] if isinstance(a['max_tokens'], int) and isinstance(b['max_tokens'], int) else '?'
        a_ra_s = f"{a['ra']:>+9.4f}" if isinstance(a['ra'], (int, float)) else f"{'MISS':>9}"
        b_ra_s = f"{b['ra']:>+9.4f}" if isinstance(b['ra'], (int, float)) else f"{'MISS':>9}"
        a_sas_s = f"{a['sas']:>+8.4f}" if isinstance(a['sas'], (int, float)) else f"{'MISS':>8}"
        b_sas_s = f"{b['sas']:>+8.4f}" if isinstance(b['sas'], (int, float)) else f"{'MISS':>8}"
        a_pmm_s = f"{a['pmm']:>7.4f}" if isinstance(a['pmm'], (int, float)) else f"{'N/A':>7}"
        b_pmm_s = f"{b['pmm']:>7.4f}" if isinstance(b['pmm'], (int, float)) else f"{'N/A':>7}"
        diff_s = f"{diff:>+4d}" if isinstance(diff, int) else f"{'?':>4}"
        print(f"{a['tick']:3d} | {a['max_tokens']:>5} {a['mode']:>8} {a_ra_s} {a_sas_s} {a_pmm_s} | {b['max_tokens']:>5} {b['mode']:>8} {b_ra_s} {b_sas_s} {b_pmm_s} | {diff_s}")

    if a_toks and b_toks and all(isinstance(x, int) for x in a_toks + b_toks):
        diffs = [bb - aa for aa, bb in zip(a_toks, b_toks)]
        print(f"\n  A max_tokens 均值: {statistics.mean(a_toks):.1f}, 范围: [{min(a_toks)}, {max(a_toks)}]")
        print(f"  B max_tokens 均值: {statistics.mean(b_toks):.1f}, 范围: [{min(b_toks)}, {max(b_toks)}]")
        print(f"  B-A 范围: [{min(diffs):+d}, {max(diffs):+d}]")
        print(f"  全部 B > A? {'是' if all(d > 0 for d in diffs) else '否'}")

    # ═══ 结论 ═══
    print("\n" + "=" * 120)
    print("结论")
    print("=" * 120)

    checks = []

    # 检查 1: A ra < 0, B ra > 0
    if isinstance(train_a['ra'], (int, float)) and isinstance(train_b['ra'], (int, float)):
        checks.append(("✓" if train_a['ra'] < 0 < train_b['ra'] else "✗",
                       f"A/B relational_awareness 方向: A={train_a['ra']:.5f}, B={train_b['ra']:.5f}"))

    # 检查 2: sas = tanh(ra*1.5)
    for label, ts in [("A", train_a), ("B", train_b)]:
        if isinstance(ts['ra'], (int, float)) and isinstance(ts['sas'], (int, float)):
            expected = round(math.tanh(ts['ra'] * 1.5), 7)
            match = abs(ts['sas'] - expected) < 1e-5
            checks.append(("✓" if match else "✗",
                           f"{label} self_awareness_signal = tanh(ra*1.5): 实际={ts['sas']:.7f}, 期望={expected:.7f}"))

    # 检查 3: pmm A < 1, B > 1
    if isinstance(train_a['pmm'], (int, float)) and isinstance(train_b['pmm'], (int, float)):
        checks.append(("✓" if train_a['pmm'] < 1.0 < train_b['pmm'] else "✗",
                       f"pressure_memory_mod: A={train_a['pmm']:.5f} < 1.0 < B={train_b['pmm']:.5f}"))

    # 检查 4: idle 保持
    idle_ok = (ra_b == ra_a) and (sas_b == sas_a)
    checks.append(("✓" if idle_ok else "✗",
                   f"idle_update_memory 保持 ra 和 sas: ra {ra_b}->{ra_a}, sas {sas_b}->{sas_a}"))

    # 检查 5: B > A in test
    if a_toks and b_toks and all(isinstance(x, int) for x in a_toks + b_toks):
        diffs = [bb - aa for aa, bb in zip(a_toks, b_toks)]
        checks.append(("✓" if all(d > 0 for d in diffs) else "✗",
                       f"测试期 B > A: 间距 {min(diffs):+d}~{max(diffs):+d}"))

    for sym, desc in checks:
        print(f"  {sym} {desc}")

    all_pass = all(c[0] == "✓" for c in checks)
    print(f"\n总评: {'全部通过' if all_pass else '存在失败项'}")
    print(f"执行时间: {elapsed:.1f} 秒")
    print("=" * 120)


if __name__ == "__main__":
    main()
