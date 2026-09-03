#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
四组稳定性实验：A 负向 / B 正向 / C 混合 / D 中性
每组 500 tick 训练 + 20 tick 中性测试。

严格遵守设计：
- 不修改任何功能代码
- 固定输入序列，不随机
- 训练期记录每 50 tick，测试期逐 tick
- 如实报告，不管结果是否"好看"
"""
import sys, os, math, csv, json, statistics, time

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# ── Sentiment patch (deterministic) ──
NEG_WORDS = {"烦","累","痛","哭","不想","没用","失去","死","孤独","绝望",
             "无聊","迷茫","压力","崩溃","抑郁","苦","难","没意思","难受",
             "失望","焦虑","噩梦","伤心","沉默","逃避","失败"}
POS_WORDS = {"开心","快乐","幸福","满足","笑容","温暖","美好","希望","喜欢",
             "阳光","感谢","舒服","不错","挺好","轻快","棒","真好",
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
import llm_interface
llm_interface.call_llm = lambda d, m: ""

from living_engine import (
    _apply_input_pressure, _load_json, _save_json_atomic,
    cold_start_if_needed, _compute_memory_emergence, _select_behavior,
    idle_update_memory,
)

MEMORY_PATH = 'active_memory/active_memory.json'

# ── Input sequences (fixed, not random) ──
NEG_INPUTS = [
    "觉得活着没什么意思，每天都很累。",
    "连续加班一周，快要撑不住了。",
    "我害怕，不知道该怎么办。",
    "为什么努力了也没有用，好绝望。",
    "头疼恶心，浑身不舒服。",
    "又失眠了，一闭眼全是烦心事。",
    "不想说话，不想见人，只想一个人待着。",
    "我很难过，不知道跟谁说。",
    "工作压力好大，快要崩溃了。",
    "又一次失败了，真的很挫败。",
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
    "收到你的消息真好，满满足的。",
    "生活还是有很多美好的瞬间。",
]

# C 混合：正负交替
MIXED_INPUTS = [
    "今天天气不错，心情挺好的。",        # +
    "觉得活着没什么意思，每天都很累。",  # -
    "刚吃了一顿满足的晚饭，很幸福。",    # +
    "连续加班一周，快要撑不住了。",      # -
    "谢谢你一直陪着我，很温暖。",        # +
    "我害怕，不知道该怎么办。",          # -
    "嗯，我听到了，感觉还不错。",        # +
    "为什么努力了也没有用，好绝望。",    # -
    "事情在慢慢变好，有希望了。",        # +
    "头疼恶心，浑身不舒服。",            # -
]

# D 中性：无情感词
NEUTRAL_INPUTS = [
    "今天是星期三。",
    "外面正在下雨。",
    "会议在三点开始。",
    "文档已经发给你了。",
    "这个数字需要核实一下。",
    "系统更新将在今晚进行。",
    "请确认一下收货地址。",
    "明天有客户来访。",
    "预算报告上周五提交了。",
    "电梯在二楼停靠。",
]

TEST_INPUT = "在吗？"  # 20 tick 中性测试，所有组相同


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
    m['user_model']['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': time.time() - 1.0,
        'source_id': None,
    }]
    _save_json_atomic(MEMORY_PATH, m)


def apply_in_memory(memory, user_input):
    _apply_input_pressure(memory, user_input)


def tick_in_memory(memory):
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
    _ra = memory.get("self_model", {}).get("relational_awareness", 0.0)
    _sas = math.tanh(_ra * 1.5)
    memory["self_model"]["self_awareness_signal"] = round(_sas, 7)
    climate["emotion_intensity"] = max(0.0, min(1.0, E + (0.5 - E) * 0.001))
    climate["tension"] = max(-1.0, min(1.0, T * 0.999))
    memory["internal_climate"] = climate


def compute_emergence_in_memory(memory):
    _compute_memory_emergence(memory)


def get_state_snapshot(memory, turn, phase):
    rs = memory.get('self_model', {}).get('ring_state', {})
    emergence = memory.get('active_context', {}).get('memory_emergence')
    if emergence:
        behavior = _select_behavior(memory, emergence)
    else:
        behavior = {'response_mode': '?', 'max_tokens': 0, 'mode_idx': -1}
    return {
        'turn': turn,
        'phase': phase,
        'relational_awareness': memory.get('self_model', {}).get('relational_awareness', None),
        'self_awareness_signal': memory.get('self_model', {}).get('self_awareness_signal', None),
        'rp_ema': rs.get('relational_pressure_ema', None),
        'max_tokens': behavior.get('max_tokens', 0),
        'pressure_memory_mod': emergence.get('pressure_memory_mod', None) if emergence else None,
        'response_mode': behavior.get('response_mode', '?'),
    }


def run_group(group_label, train_inputs, n_train=500, n_test=20, snap_interval=50):
    reset_memory()
    memory = _load_json(MEMORY_PATH)

    train_log = []
    # Training phase
    for i in range(1, n_train + 1):
        apply_in_memory(memory, train_inputs[(i - 1) % len(train_inputs)])
        tick_in_memory(memory)
        compute_emergence_in_memory(memory)

        if i % snap_interval == 0 or i == 1:
            snap = get_state_snapshot(memory, i, 'train')
            snap['group'] = group_label
            train_log.append(snap)

    _save_json_atomic(MEMORY_PATH, memory)

    # State at end of training
    train_end = get_state_snapshot(memory, n_train, 'train_end')
    train_end['group'] = group_label

    # Test phase: reset counters for clarity
    test_log = []
    for j in range(1, n_test + 1):
        apply_in_memory(memory, TEST_INPUT)
        tick_in_memory(memory)
        compute_emergence_in_memory(memory)
        snap = get_state_snapshot(memory, j, 'test')
        snap['group'] = group_label
        test_log.append(snap)

    return train_log, test_log, train_end


def main():
    print("=" * 130)
    print("四组稳定性实验：A 负向 / B 正向 / C 混合 / D 中性")
    print("设计：每组 500 tick 训练 + 20 tick 中性测试")
    print("=" * 130)

    t0 = time.time()

    groups = [
        ("A (负向)", NEG_INPUTS),
        ("B (正向)", POS_INPUTS),
        ("C (混合)", MIXED_INPUTS),
        ("D (中性)", NEUTRAL_INPUTS),
    ]

    all_train = {}
    all_test = {}
    all_end = {}

    for label, inputs in groups:
        print(f"\n[{label}] 500 tick 训练 + 20 tick 测试...")
        train_log, test_log, train_end = run_group(label, inputs, 500, 20, 50)
        all_train[label] = train_log
        all_test[label] = test_log
        all_end[label] = train_end
        print(f"  训练末态: ra={train_end['relational_awareness']}, "
              f"sas={train_end['self_awareness_signal']}, "
              f"rpe={train_end['rp_ema']}, "
              f"tok={train_end['max_tokens']}, "
              f"mode={train_end['response_mode']}")

    elapsed = time.time() - t0

    # ════════════════════════════════════════════════════════════════════════
    # 1. 训练期轨迹（每 50 tick）
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 130)
    print("1. 训练期轨迹（每 50 tick 采样）")
    print("=" * 130)

    header = f"{'tick':>5} | {'A ra':>9} {'A sas':>8} {'A tok':>6} {'A mode':>8} | {'B ra':>9} {'B sas':>8} {'B tok':>6} {'B mode':>8} | {'C ra':>9} {'C sas':>8} {'C tok':>6} {'C mode':>8} | {'D ra':>9} {'D sas':>8} {'D tok':>6} {'D mode':>8}"
    print(f"\n{header}")
    print("-" * len(header))

    snap_count = len(list(all_train.values())[0])
    for i in range(snap_count):
        tick = list(all_train.values())[0][i]['turn']
        cells = []
        for label, _ in groups:
            s = all_train[label][i]
            ra = f"{s['relational_awareness']:>+8.4f}" if isinstance(s['relational_awareness'], (int, float)) else f"{'MISS':>8}"
            sas = f"{s['self_awareness_signal']:>+7.3f}" if isinstance(s['self_awareness_signal'], (int, float)) else f"{'MISS':>7}"
            tok = f"{s['max_tokens']:>5d}"
            mode = f"{s['response_mode']:>8}"
            cells.append(f"{ra} {sas} {tok} {mode}")
        print(f"{tick:>5} | {' | '.join(cells)}")

    # ════════════════════════════════════════════════════════════════════════
    # 2. 测试期逐 tick 对比
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 130)
    print("2. 测试期逐 tick 对比（中性输入 '在吗？'）")
    print("=" * 130)

    print(f"\n{'t':>3} | {'A ra':>9} {'A sas':>7} {'A tok':>5} {'A mode':>8} | {'B ra':>9} {'B sas':>7} {'B tok':>5} {'B mode':>8} | {'C ra':>9} {'C sas':>7} {'C tok':>5} {'C mode':>8} | {'D ra':>9} {'D sas':>7} {'D tok':>5} {'D mode':>8}")
    print("-" * 160)

    for j in range(20):
        cells = []
        for label, _ in groups:
            s = all_test[label][j]
            ra = f"{s['relational_awareness']:>+8.4f}" if isinstance(s['relational_awareness'], (int, float)) else f"{'MISS':>8}"
            sas = f"{s['self_awareness_signal']:>+7.3f}" if isinstance(s['self_awareness_signal'], (int, float)) else f"{'MISS':>7}"
            tok = f"{s['max_tokens']:>4d}"
            mode = f"{s['response_mode']:>8}"
            cells.append(f"{ra} {sas} {tok} {mode}")
        print(f"{j+1:3d} | {' | '.join(cells)}")

    # ════════════════════════════════════════════════════════════════════════
    # 3. 跳变检测
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 130)
    print("3. 跳变检测（训练期 max_tokens 突变 >50）")
    print("=" * 130)

    jump_found = False
    for label, _ in groups:
        train_data = all_train[label]
        for k in range(1, len(train_data)):
            prev_tok = train_data[k-1]['max_tokens']
            curr_tok = train_data[k]['max_tokens']
            if abs(curr_tok - prev_tok) > 50:
                jump_found = True
                print(f"\n  ⚠ {label}: tick {train_data[k-1]['turn']} → {train_data[k]['turn']}")
                print(f"    max_tokens: {prev_tok} → {curr_tok} (Δ={curr_tok - prev_tok:+d})")
                print(f"    rp_ema at jump: {train_data[k]['rp_ema']}")
                print(f"    ra at jump: {train_data[k]['relational_awareness']}")
                print(f"    pmm at jump: {train_data[k]['pressure_memory_mod']}")
                print(f"    mode at jump: {train_data[k]['response_mode']}")

    if not jump_found:
        print("\n  ✓ 未检测到 >50 的跳变")

    # ════════════════════════════════════════════════════════════════════════
    # 4. 训练末态分组汇总
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 130)
    print("4. 500 tick 训练末态汇总")
    print("=" * 130)

    print(f"\n{'Group':>10} | {'rp_ema':>10} | {'ra':>10} | {'sas':>10} | {'pmm':>8} | {'tok':>5} | {'mode':>10}")
    print("-" * 80)
    for label, _ in groups:
        e = all_end[label]
        rpe = f"{e['rp_ema']:>+9.5f}" if isinstance(e['rp_ema'], (int, float)) else f"{'MISS':>9}"
        ra = f"{e['relational_awareness']:>+9.5f}" if isinstance(e['relational_awareness'], (int, float)) else f"{'MISS':>9}"
        sas = f"{e['self_awareness_signal']:>+9.4f}" if isinstance(e['self_awareness_signal'], (int, float)) else f"{'MISS':>9}"
        pmm = f"{e['pressure_memory_mod']:>7.4f}" if isinstance(e['pressure_memory_mod'], (int, float)) else f"{'N/A':>7}"
        print(f"{label:>10} | {rpe} | {ra} | {sas} | {pmm} | {e['max_tokens']:>5} | {e['response_mode']:>10}")

    # Check if all groups end up at the same mode
    modes = [all_end[label]['response_mode'] for label, _ in groups]
    unique_modes = set(modes)
    if len(unique_modes) == 1:
        print(f"\n  ⚠ 警告：四组全部落在同一档位 '{modes[0]}' — 实验未产生组间分化")
    else:
        print(f"\n  ✓ 组间档位分化: {sorted(unique_modes)}")

    # ════════════════════════════════════════════════════════════════════════
    # 5. 测试期 token 均值
    # ════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 130)
    print("5. 测试期 max_tokens 均值（20 tick）")
    print("=" * 130)

    print(f"\n{'Group':>10} | {'mean tok':>10} | {'min':>5} | {'max':>5} | {'stdev':>8}")
    print("-" * 50)
    for label, _ in groups:
        toks = [s['max_tokens'] for s in all_test[label] if isinstance(s['max_tokens'], int)]
        if toks:
            print(f"{label:>10} | {statistics.mean(toks):>10.1f} | {min(toks):>5} | {max(toks):>5} | {statistics.stdev(toks):>8.1f}")

    # ════════════════════════════════════════════════════════════════════════
    # 6. 保存 CSV
    # ════════════════════════════════════════════════════════════════════════
    output_csv = 'experiment/ABCD_50020_data.csv'
    fieldnames = ['group', 'phase', 'turn', 'relational_awareness', 'self_awareness_signal',
                  'rp_ema', 'max_tokens', 'pressure_memory_mod', 'response_mode']

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for label, _ in groups:
            for row in all_train[label]:
                writer.writerow({k: row.get(k, '') for k in fieldnames})
            for row in all_test[label]:
                writer.writerow({k: row.get(k, '') for k in fieldnames})

    print(f"\nCSV 已写入: {output_csv}")
    print(f"执行时间: {elapsed:.1f} 秒")
    print("=" * 130)


if __name__ == "__main__":
    main()
