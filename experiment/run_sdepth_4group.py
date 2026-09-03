#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s_depth 参数校准实验：四组 P/G_pos_neg/G_neg_pos/D。
参数：alpha=0.004, gamma=0.0001。
"""
import sys, os, time, json, csv, math, hashlib

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

import llm_interface
llm_interface.call_llm = lambda d, m: ""

NEG_WORDS = {"烦","累","痛","哭","不想","没用","失去","死","孤独","绝望",
             "无聊","迷茫","压力","崩溃","抑郁","苦","难","没意思","难受",
             "失望","焦虑","噩梦","伤心","沉默","逃避","失败","挫败"}
POS_WORDS = {"开心","快乐","幸福","满足","笑容","温暖","美好","希望","喜欢",
             "阳光","感谢","不错","挺好","轻快","棒","真好",
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
    cold_start_if_needed, _compute_memory_emergence,
    _update_luoshen_coupled, _encode_episodic_memory,
    _select_behavior,
)
from run_r_experiment import POSITIVE_INPUTS, NEGATIVE_INPUTS, NEUTRAL_INPUTS, SYNTHETIC_ENV, reset_memory, get_snapshot

def pearson(a, b):
    n = len(a)
    if n < 2: return 0.0
    ma, mb = sum(a)/n, sum(b)/n
    num = sum((x-ma)*(y-mb) for x, y in zip(a,b))
    da = math.sqrt(sum((x-ma)**2 for x in a))
    db = math.sqrt(sum((y-mb)**2 for y in b))
    if da < 1e-12 or db < 1e-12: return 0.0
    return num / (da * db)

def run_group(gname, base_inputs, total_ticks, switch_to=None, exp_dir="experiment"):
    state_path = os.path.join(exp_dir, f"sd_exp_{gname}.json")
    reset_memory(state_path)
    memory = _load_json(state_path)

    phase = "train"
    rows = []
    switch_tick = total_ticks // 2 if switch_to else total_ticks + 1  # default: switch at midpoint for 1000-tick groups

    for i in range(1, total_ticks + 1):
        if i == switch_tick + 1 and switch_to is not None:
            phase = "post_switch"

        inp_seq = base_inputs if i <= switch_tick else (switch_to if switch_to else base_inputs)
        inp = inp_seq[(i - 1) % len(inp_seq)]

        _apply_input_pressure(memory, inp)
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (i % 86400) / 86400.0
        _update_luoshen_coupled(memory, env, tick_id=i)
        _encode_episodic_memory(memory)
        em = _compute_memory_emergence(memory)
        behavior = _select_behavior(memory, em)
        snap = get_snapshot(memory)

        rs = memory['self_model']['ring_state']
        row = {
            'tick': i, 'group': gname, 'phase': phase,
            'input_type': 'positive' if inp_seq is base_inputs and i <= switch_tick else ('negative' if switch_to else 'neutral'),
            'rp_ema': snap.get('rp_ema'),
            's_depth': rs.get('s_depth'),
            'mode': behavior.get('response_mode'),
            'max_tokens': behavior.get('max_tokens'),
            'E': snap.get('E'), 'T': snap.get('T'), 'N': snap.get('N'),
        }

        # Sampling logic
        record = False
        if gname in ('P', 'D'):
            if i % 50 == 0 or i in (1, 5, 10):
                record = True
        else:
            # G groups: dense first 100 of post-switch, then every 50
            if i <= switch_tick:
                if i % 50 == 0 or i in (1, 5, 10):
                    record = True
            else:
                # post-switch: dense sampling
                dense_ticks = {501, 505, 510, 515, 520, 530, 540, 550, 560, 580, 600}
                if i in dense_ticks or i % 50 == 0:
                    record = True

        if record:
            rows.append(row)

        _save_json_atomic(state_path, memory)

    return rows

def main():
    exp_dir = "experiment"
    os.makedirs(exp_dir, exist_ok=True)

    groups = {
        'P':        (POSITIVE_INPUTS, 500, None),
        'G_pos_neg':(POSITIVE_INPUTS, 1000, NEGATIVE_INPUTS),
        'G_neg_pos':(NEGATIVE_INPUTS, 1000, POSITIVE_INPUTS),
        'D':        (NEUTRAL_INPUTS, 500, None),
    }

    all_logs = {}
    for gname, (base, ticks, sw) in groups.items():
        print(f"Running {gname} ({ticks} ticks, switch={'yes' if sw else 'no'})...")
        all_logs[gname] = run_group(gname, base, ticks, switch_to=sw, exp_dir=exp_dir)

    # Write CSVs
    for gname, rows in all_logs.items():
        p = os.path.join(exp_dir, f"sd_exp_{gname}_data.csv")
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction='ignore')
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"  {gname}: {p}  rows={len(rows)}")

    # Metrics
    print()
    print("=" * 60)
    print("Calibrated s_depth metrics")
    print("=" * 60)

    # corr(s_depth, rp_ema) across all
    all_s, all_r = [], []
    for rows in all_logs.values():
        for r in rows:
            if r.get('s_depth') is not None and r.get('rp_ema') is not None:
                all_s.append(r['s_depth']); all_r.append(r['rp_ema'])
    c = pearson(all_s, all_r)
    print(f"corr(s_depth, rp_ema) = {c:.4f}")
    print(f" 判定: {'PASS' if abs(c) < 0.3 else 'FAIL'}  (|corr| < 0.3)")
    print()

    # P_500
    p_last = all_logs['P'][-1]
    p_sd = p_last.get('s_depth')
    print(f"P_500 tick={p_last['tick']}: s_depth={p_sd}")
    p_pass = p_sd is not None and p_sd >= 0.3
    print(f" 判定: {'PASS' if p_pass else 'FAIL'} (s_depth >= 0.3)")
    p_avg_rpe = sum(r['rp_ema'] for r in all_logs['P']) / len(all_logs['P'])
    p_avg_e = sum(r['rp_ema']**2 for r in all_logs['P']) / len(all_logs['P'])
    print(f"  avg rp_ema = {p_avg_rpe:+.4f}, avg engagement(rp_ema²) = {p_avg_e:.4f}")
    print()

    # G_pos_neg
    gpn_last = all_logs['G_pos_neg'][-1]
    gpn_sd = gpn_last.get('s_depth'); gpn_mode = gpn_last.get('mode'); gpn_tok = gpn_last.get('max_tokens')
    print(f"G_pos_neg tick={gpn_last['tick']}: s_depth={gpn_sd}, mode={gpn_mode}, max_tokens={gpn_tok}")
    gpn_a = gpn_sd is not None and gpn_sd >= 0.6
    gpn_b = gpn_mode == 'normal'
    gpn_c = gpn_tok is not None and gpn_tok >= 120
    print(f"  s_depth >= 0.6: {'PASS' if gpn_a else 'FAIL'}")
    print(f"  mode = normal: {'PASS' if gpn_b else 'FAIL'}")
    print(f"  max_tokens >= 120: {'PASS' if gpn_c else 'FAIL'}")
    print()

    # G_neg_pos
    gnp_last = all_logs['G_neg_pos'][-1]
    gnp_sd = gnp_last.get('s_depth'); gnp_mode = gnp_last.get('mode'); gnp_tok = gnp_last.get('max_tokens')
    print(f"G_neg_pos tick={gnp_last['tick']}: s_depth={gnp_sd}, mode={gnp_mode}, max_tokens={gnp_tok}")
    gnp_a = gnp_sd is not None and gnp_sd >= 0.6
    gnp_b = gnp_mode == 'normal'
    gnp_c = gnp_tok is not None and gnp_tok >= 120
    print(f"  s_depth >= 0.6: {'PASS' if gnp_a else 'FAIL'}")
    print(f"  mode = normal: {'PASS' if gnp_b else 'FAIL'}")
    print(f"  max_tokens >= 120: {'PASS' if gnp_c else 'FAIL'}")
    print()

    # D_500
    d_last = all_logs['D'][-1]
    d_sd = d_last.get('s_depth')
    print(f"D_500 tick={d_last['tick']}: s_depth={d_sd}")
    d_pass = d_sd is not None and d_sd < 0.05
    print(f"  判定: {'PASS' if d_pass else 'FAIL'} (s_depth < 0.05)")
    print()

    all_pass = abs(c) < 0.3 and p_pass and gpn_a and gpn_b and gpn_c and gnp_a and gnp_b and gnp_c and d_pass
    print(f"ALL PASS: {all_pass}")

    # Save summary
    summary = {
        'alpha_accum': 0.004, 'gamma_decay': 0.0001, 'dt': 0.08,
        'corr': round(c, 4),
        'P_sdepth': p_sd, 'G_posneg_sdepth': gpn_sd, 'G_negpos_sdepth': gnp_sd,
        'D_sdepth': d_sd,
        'all_pass': all_pass,
    }
    sp = os.path.join(exp_dir, "sdepth_calib_summary.json")
    with open(sp, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Summary: {sp}")

if __name__ == '__main__':
    main()
