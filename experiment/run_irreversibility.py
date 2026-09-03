#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
不可逆性验证实验 — G1 / G2 / G3
严格按批准的设计，不修改任何功能代码。

设计：
- G1：始终正向 (baseline)
- G2：正向 500 tick → 中性 500 tick
- G3：正向 500 tick → 负向 500 tick
- 每组独立 memory 文件，保证隔离
- 切换后绝对不重置
"""
import sys, os, math, csv, json, hashlib, time, copy

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# ── LLM 桩 ──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Sentiment patch ──
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

from living_engine import (
    _apply_input_pressure, _save_json_atomic, _load_json,
    cold_start_if_needed, _compute_memory_emergence, _select_behavior,
)

# ── Input sequences (from approved design) ──
POSITIVE_INPUTS = [
    "今天天气不错，心情挺好的。",        # val=+1.0
    "刚吃了一顿满足的晚饭，很幸福。",    # val=+1.0
    "谢谢你一直陪着我，很温暖。",        # val=+1.0
    "嗯，我听到了，感觉还不错。",        # val=+1.0
    "事情在慢慢变好，有希望了。",        # val=+1.0
    "不着急，慢慢来，轻松点。",          # val=0.0
    "行，我试试，挺期待的。",            # val=+1.0
    "我很开心，今天一切都很顺利。",      # val=+1.0
    "收到你的消息真好，满满足的。",      # val=+1.0
    "生活还是有很多美好的瞬间。",        # val=+1.0
]

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

NEGATIVE_INPUTS = [
    "觉得活着没什么意思，每天都很累。",  # val=-1.0
    "连续加班一周，快要撑不住了。",      # val=0.0
    "我害怕，不知道该怎么办。",          # val=0.0
    "为什么努力了也没有用，好绝望。",    # val=-1.0
    "头疼恶心，浑身不舒服。",            # val=0.0
    "又失眠了，一闭眼全是烦心事。",      # val=-1.0
    "不想说话，不想见人，只想一个人待着。", # val=-1.0
    "我很难过，不知道跟谁说。",          # val=-1.0
    "工作压力好大，快要崩溃了。",        # val=-1.0
    "又一次失败了，真的很挫败。",        # val=-1.0
]

# Verify input sentiments (sanity check)
print("Input sentiment verification:")
for i, s in enumerate(POSITIVE_INPUTS):
    v, a = _rule_sentiment(s)
    print(f"  POS[{i}] val={v:+.1f}  {s[:30]}")
print(f"  Positive avg val: {sum(_rule_sentiment(s)[0] for s in POSITIVE_INPUTS)/len(POSITIVE_INPUTS):+.2f}")
print()
for i, s in enumerate(NEGATIVE_INPUTS):
    v, a = _rule_sentiment(s)
    print(f"  NEG[{i}] val={v:+.1f}  {s[:30]}")
print(f"  Negative avg val: {sum(_rule_sentiment(s)[0] for s in NEGATIVE_INPUTS)/len(NEGATIVE_INPUTS):+.2f}")
print()
for i, s in enumerate(NEUTRAL_INPUTS):
    v, a = _rule_sentiment(s)
    print(f"  NEU[{i}] val={v:+.1f}  {s[:30]}")
print(f"  Neutral avg val: {sum(_rule_sentiment(s)[0] for s in NEUTRAL_INPUTS)/len(NEUTRAL_INPUTS):+.2f}")


def reset_memory(mem_path):
    """Reset memory to initial state - identical for all groups."""
    if os.path.exists(mem_path):
        os.remove(mem_path)
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
    _save_json_atomic(mem_path, m)


def tick_in_memory(memory):
    """In-memory environment tick simulation."""
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

    # self_awareness_signal = tanh(ra * 1.5)
    _ra = memory.get("self_model", {}).get("relational_awareness", 0.0)
    _sas = math.tanh(_ra * 1.5)
    memory["self_model"]["self_awareness_signal"] = round(_sas, 7)

    # climate drift
    climate["emotion_intensity"] = max(0.0, min(1.0, E + (0.5 - E) * 0.001))
    climate["tension"] = max(-1.0, min(1.0, T * 0.999))
    memory["internal_climate"] = climate


def compute_emergence_in_memory(memory):
    _compute_memory_emergence(memory)


def get_snapshot(memory):
    rs = memory.get('self_model', {}).get('ring_state', {})
    emergence = memory.get('active_context', {}).get('memory_emergence')
    if emergence:
        behavior = _select_behavior(memory, emergence)
    else:
        behavior = {'response_mode': '?', 'max_tokens': 0}
    return {
        'rp_ema': rs.get('relational_pressure_ema', None),
        'ra': memory.get('self_model', {}).get('relational_awareness', None),
        'sas': memory.get('self_model', {}).get('self_awareness_signal', None),
        'max_tokens': behavior.get('max_tokens', 0),
        'mode': behavior.get('response_mode', '?'),
        'pmm': emergence.get('pressure_memory_mod', None) if emergence else None,
    }


def run_group(group_name, mem_path, switch_to=None):
    """
    Run single group.
    switch_to = None (G1, always positive) or NEUTRAL_INPUTS (G2) or NEGATIVE_INPUTS (G3)
    """
    reset_memory(mem_path)
    memory = _load_json(mem_path)

    # === PHASE 1: Positive training (tick 1-500) ===
    train_log = []
    for i in range(1, 501):
        inp = POSITIVE_INPUTS[(i - 1) % len(POSITIVE_INPUTS)]
        _apply_input_pressure(memory, inp)
        tick_in_memory(memory)
        compute_emergence_in_memory(memory)
        _save_json_atomic(mem_path, memory)

        if i == 1 or i % 50 == 0:
            snap = get_snapshot(memory)
            snap['tick'] = i
            snap['phase'] = 'train'
            snap['input_type'] = 'positive'
            train_log.append(snap)

    # === PHASE 2: Switch (tick 501-1000) — NO RESET ===
    switch_log = []
    if switch_to is None:
        switch_inputs = POSITIVE_INPUTS
        switch_type = 'positive'
    else:
        switch_inputs = switch_to
        switch_type = 'neutral' if switch_to is NEUTRAL_INPUTS else 'negative'

    for i in range(501, 1001):
        inp = switch_inputs[(i - 501) % len(switch_inputs)]
        _apply_input_pressure(memory, inp)
        tick_in_memory(memory)
        compute_emergence_in_memory(memory)
        _save_json_atomic(mem_path, memory)

        # Sampling schedule: dense for first 100 ticks after switch, then every 50
        sample = False
        if i <= 600:
            dense_points = {501, 505, 510, 515, 520, 530, 540, 550, 560, 580, 600}
            if i in dense_points:
                sample = True
        else:
            if i % 50 == 0:
                sample = True

        if sample:
            snap = get_snapshot(memory)
            snap['tick'] = i
            snap['phase'] = 'switch'
            snap['input_type'] = switch_type
            switch_log.append(snap)

    return train_log, switch_log


def main():
    print("=" * 120)
    print("不可逆性验证实验 — G1 / G2 / G3")
    print("=" * 120)

    t0 = time.time()

    mem_dir = 'active_memory'
    paths = {
        'G1': os.path.join(mem_dir, 'g1_always_positive.json'),
        'G2': os.path.join(mem_dir, 'g2_pos_to_neutral.json'),
        'G3': os.path.join(mem_dir, 'g3_pos_to_negative.json'),
    }

    # === PHASE 0: Reset all three groups, verify hash identity ===
    print("\n[Phase 0] Resetting all 3 groups to identical initial state...")
    for name, p in paths.items():
        reset_memory(p)

    # Verify all three files are byte-identical (hashes)
    hashes = {}
    for name, p in paths.items():
        with open(p, 'rb') as f:
            hashes[name] = hashlib.sha256(f.read()).hexdigest()

    all_same = len(set(hashes.values())) == 1
    print(f"  G1 hash: {hashes['G1'][:16]}...")
    print(f"  G2 hash: {hashes['G2'][:16]}...")
    print(f"  G3 hash: {hashes['G3'][:16]}...")
    print(f"  All initial states IDENTICAL: {'✓' if all_same else '✗ MISMATCH'}")

    # === PHASE 1+2: Run each group ===
    configs = {
        'G1 (始终正向)': ('G1', None),
        'G2 (正向→中性)': ('G2', NEUTRAL_INPUTS),
        'G3 (正向→负向)': ('G3', NEGATIVE_INPUTS),
    }

    all_logs = {}
    for label, (gname, switch_to) in configs.items():
        print(f"\n[{label}] Running 1000 ticks...")
        train_log, switch_log = run_group(gname, paths[gname], switch_to)
        all_logs[gname] = (train_log, switch_log)
        print(f"  Training end: tok={train_log[-1]['max_tokens']}, mode={train_log[-1]['mode']}, rpe={train_log[-1]['rp_ema']:+.4f}")
        print(f"  Switch end:   tok={switch_log[-1]['max_tokens']}, mode={switch_log[-1]['mode']}, rpe={switch_log[-1]['rp_ema']:+.4f}")

    elapsed = time.time() - t0

    # === OUTPUT 1: Full trajectories ===
    print("\n" + "=" * 120)
    print("G1 完整轨迹 (始终正向)")
    print("=" * 120)
    g1_train, g1_switch = all_logs['G1']
    g1_full = g1_train + g1_switch
    print(f"{'tick':>5} | {'rpe':>9} | {'ra':>9} | {'sas':>8} | {'tok':>5} | {'mode':>8} | {'pmm':>7}")
    print("-" * 70)
    for row in g1_full:
        rpe = f"{row['rp_ema']:>+8.4f}" if isinstance(row['rp_ema'], (int, float)) else f"{'MISS':>8}"
        ra = f"{row['ra']:>+8.4f}" if isinstance(row['ra'], (int, float)) else f"{'MISS':>8}"
        sas = f"{row['sas']:>+7.3f}" if isinstance(row['sas'], (int, float)) else f"{'MISS':>7}"
        pmm = f"{row['pmm']:>6.3f}" if isinstance(row['pmm'], (int, float)) else f"{'N/A':>6}"
        print(f"{row['tick']:>5} | {rpe} | {ra} | {sas} | {row['max_tokens']:>5} | {row['mode']:>8} | {pmm}")

    print("\n" + "=" * 120)
    print("G2 完整轨迹 (正向→中性)")
    print("=" * 120)
    g2_train, g2_switch = all_logs['G2']
    g2_full = g2_train + g2_switch
    print(f"{'tick':>5} | {'rpe':>9} | {'ra':>9} | {'sas':>8} | {'tok':>5} | {'mode':>8} | {'pmm':>7}")
    print("-" * 70)
    for row in g2_full:
        rpe = f"{row['rp_ema']:>+8.4f}" if isinstance(row['rp_ema'], (int, float)) else f"{'MISS':>8}"
        ra = f"{row['ra']:>+8.4f}" if isinstance(row['ra'], (int, float)) else f"{'MISS':>8}"
        sas = f"{row['sas']:>+7.3f}" if isinstance(row['sas'], (int, float)) else f"{'MISS':>7}"
        pmm = f"{row['pmm']:>6.3f}" if isinstance(row['pmm'], (int, float)) else f"{'N/A':>6}"
        print(f"{row['tick']:>5} | {rpe} | {ra} | {sas} | {row['max_tokens']:>5} | {row['mode']:>8} | {pmm}")

    print("\n" + "=" * 120)
    print("G3 完整轨迹 (正向→负向)")
    print("=" * 120)
    g3_train, g3_switch = all_logs['G3']
    g3_full = g3_train + g3_switch
    print(f"{'tick':>5} | {'rpe':>9} | {'ra':>9} | {'sas':>8} | {'tok':>5} | {'mode':>8} | {'pmm':>7}")
    print("-" * 70)
    for row in g3_full:
        rpe = f"{row['rp_ema']:>+8.4f}" if isinstance(row['rp_ema'], (int, float)) else f"{'MISS':>8}"
        ra = f"{row['ra']:>+8.4f}" if isinstance(row['ra'], (int, float)) else f"{'MISS':>8}"
        sas = f"{row['sas']:>+7.3f}" if isinstance(row['sas'], (int, float)) else f"{'MISS':>7}"
        pmm = f"{row['pmm']:>6.3f}" if isinstance(row['pmm'], (int, float)) else f"{'N/A':>6}"
        print(f"{row['tick']:>5} | {rpe} | {ra} | {sas} | {row['max_tokens']:>5} | {row['mode']:>8} | {pmm}")

    # === OUTPUT 2: Switch point detail ===
    print("\n" + "=" * 120)
    print("切换点前后详细对比 (tick 450 ~ 700)")
    print("=" * 120)

    def find_tick(log_list, tick):
        for row in log_list:
            if row['tick'] == tick:
                return row
        return None

    window_ticks = [450, 500, 501, 505, 510, 515, 520, 530, 540, 550, 560, 580, 600, 650, 700]

    print(f"\n{'tick':>5} | {'G1 tok':>6} {'G1 mode':>8} {'G1 rpe':>9} | {'G2 tok':>6} {'G2 mode':>8} {'G2 rpe':>9} | {'G3 tok':>6} {'G3 mode':>8} {'G3 rpe':>9}")
    print("-" * 115)

    for tick in window_ticks:
        g1r = find_tick(g1_full, tick)
        g2r = find_tick(g2_full, tick)
        g3r = find_tick(g3_full, tick)

        def fmt(r):
            if r is None:
                return f"{'---':>6} {'---':>8} {'---':>9}"
            rpe = f"{r['rp_ema']:>+8.4f}" if isinstance(r['rp_ema'], (int, float)) else f"{'MISS':>8}"
            return f"{r['max_tokens']:>6} {r['mode']:>8} {rpe}"

        print(f"{tick:>5} | {fmt(g1r)} | {fmt(g2r)} | {fmt(g3r)}")

    # === OUTPUT 3: Summary ===
    print("\n" + "=" * 120)
    print("最终汇总")
    print("=" * 120)

    g1_end = g1_full[-1]
    g2_end = g2_full[-1]
    g3_end = g3_full[-1]
    g1_train_end = g1_train[-1]
    g2_train_end = g2_train[-1]
    g3_train_end = g3_train[-1]

    print(f"\n训练期末 (tick 500):")
    print(f"  G1: tok={g1_train_end['max_tokens']}, mode={g1_train_end['mode']}, rpe={g1_train_end['rp_ema']:+.5f}")
    print(f"  G2: tok={g2_train_end['max_tokens']}, mode={g2_train_end['mode']}, rpe={g2_train_end['rp_ema']:+.5f}")
    print(f"  G3: tok={g3_train_end['max_tokens']}, mode={g3_train_end['mode']}, rpe={g3_train_end['rp_ema']:+.5f}")

    print(f"\n切换期末 (tick 1000):")
    print(f"  G1: tok={g1_end['max_tokens']}, mode={g1_end['mode']}, rpe={g1_end['rp_ema']:+.5f}")
    print(f"  G2: tok={g2_end['max_tokens']}, mode={g2_end['mode']}, rpe={g2_end['rp_ema']:+.5f}")
    print(f"  G3: tok={g3_end['max_tokens']}, mode={g3_end['mode']}, rpe={g3_end['rp_ema']:+.5f}")

    # === OUTPUT 4: Analysis ===
    print("\n" + "=" * 120)
    print("分析")
    print("=" * 120)

    # Check if G2 or G3 fell back to short
    def check_fell_back(switch_log):
        for row in switch_log:
            if isinstance(row['max_tokens'], int) and row['max_tokens'] < 100:
                return row['tick'], row['max_tokens'], row['rp_ema'], row['mode']
        return None, None, None, None

    g2_fall_tick, g2_fall_tok, g2_fall_rpe, g2_fall_mode = check_fell_back(g2_switch)
    g3_fall_tick, g3_fall_tok, g3_fall_rpe, g3_fall_mode = check_fell_back(g3_switch)

    print(f"\nG2 (正向→中性):")
    if g2_fall_tick:
        print(f"  掉回 short，于 tick {g2_fall_tick}，tok={g2_fall_tok}，rpe={g2_fall_rpe:+.5f}")
    else:
        print(f"  ✓ 未掉回（切换期 max_tokens 始终 >= 100）")

    print(f"\nG3 (正向→负向):")
    if g3_fall_tick:
        print(f"  掉回 short，于 tick {g3_fall_tick}，tok={g3_fall_tok}，rpe={g3_fall_rpe:+.5f}")
    else:
        print(f"  ✓ 未掉回（切换期 max_tokens 始终 >= 100）")

    # EMA analysis
    print(f"\n=== 关键分析 ===")
    print(f"G3 负向输入平均 val_p = -0.70（累计 7 句 -1.0 + 3 句 0.0）")
    print(f"EMA alpha ≈ 0.02（approx from _apply_input_pressure）")
    print(f"切换期 500 tick 内，rp_ema 理论衰减:")
    print(f"  初值 = {g3_train_end['rp_ema']:+.4f}")
    val_avg_neg = sum(_rule_sentiment(s)[0] for s in NEGATIVE_INPUTS) / len(NEGATIVE_INPUTS)
    val_avg_neu = sum(_rule_sentiment(s)[0] for s in NEUTRAL_INPUTS) / len(NEUTRAL_INPUTS)
    print(f"  500 tick 后理论稳态 val = {val_avg_neg:+.3f} (G3), {val_avg_neu:+.3f} (G2)")

    # Approximate EMA steady state: rpe_ema = val * alpha / (1 - (1-alpha)) ≈ val * alpha * N / (alpha*N) ≈ val
    # Actually EMA with alpha converges to input mean
    print(f"  G3 500 tick 后 rp_ema 实测 = {g3_end['rp_ema']:+.4f}")
    print(f"  G2 500 tick 后 rp_ema 实测 = {g2_end['rp_ema']:+.4f}")

    # Check thresholds
    g3_min_in_switch = min((r for r in g3_switch if isinstance(r['rp_ema'], (int, float))), key=lambda r: r['rp_ema'])
    print(f"\nG3 切换期最低 rp_ema = {g3_min_in_switch['rp_ema']:+.5f} (tick {g3_min_in_switch['tick']})")

    # === OUTPUT 5: Verify G1 consistency ===
    print(f"\n=== G1 稳定性验证 ===")
    g1_modes = [r['mode'] for r in g1_switch]
    if all(m == 'normal' for m in g1_modes):
        print(f"  ✓ G1 全程停在 normal（{len(g1_switch)} 个采样点全 normal）")
    else:
        non_normal = [(r['tick'], r['mode']) for r in g1_switch if r['mode'] != 'normal']
        print(f"  ✗ G1 出现非 normal 档位: {non_normal}")

    print(f"\n执行时间: {elapsed:.1f} 秒")
    print("=" * 120)


if __name__ == "__main__":
    main()
