#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前置测试：用新输入池跑 500 tick，验证 narrative_potential 是否达标。
每 50 tick 记录：tick、mem_cnt、narrative_potential、rp_ema。
"""
import sys, os, time, json, math

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# 复用 run_r_experiment 的初始化桩和 sentiment patch
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
)

# 导入新输入池
sys.path.insert(0, os.path.join(WORKSPACE, "experiment"))
from run_r_experiment import POSITIVE_INPUTS, NEGATIVE_INPUTS, NEUTRAL_INPUTS, SYNTHETIC_ENV

# === 情感分布验证 ===
print("=" * 60)
print("新输入池情感分布验证")
print("=" * 60)
for label, seq in [("POS (len=%d)" % len(POSITIVE_INPUTS), POSITIVE_INPUTS),
                   ("NEG (len=%d)" % len(NEGATIVE_INPUTS), NEGATIVE_INPUTS),
                   ("NEU (len=%d)" % len(NEUTRAL_INPUTS), NEUTRAL_INPUTS)]:
    vals = [_rule_sentiment(s)[0] for s in seq]
    avg = sum(vals) / len(vals) if vals else 0
    print(f"  {label}: avg={avg:+.3f}")
    for s, v in zip(seq, vals):
        print(f"    {v:+.1f} | {s}")
print()

# === 500 tick 测试 ===
STATE_PATH = os.path.join(WORKSPACE, "experiment", "verify_narr.json")

def main():
    init_m = cold_start_if_needed()
    init_m['self_model']['ring_state'] = {
        'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0,
        'relational_pressure_ema': 0.0,
        'ema_amp': 0.3, 'ema_ratio': 0.3,
        'ema_pv': 0.0, 'ema_pv2': 0.0,
    }
    init_m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    init_m['user_model']['total_interactions'] = 0
    init_m['user_model']['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': time.time() - 1.0,
        'source_id': None,
    }]
    _save_json_atomic(STATE_PATH, init_m)
    memory = _load_json(STATE_PATH)

    print("=" * 60)
    print("500 tick 前置测试（新输入池，模拟正向建立期）")
    print("=" * 60)
    print("tick | mem_cnt | narrative_potential | rp_ema")
    print("----+---------+---------------------+--------")

    samples = []
    for i in range(1, 501):
        inp = POSITIVE_INPUTS[(i - 1) % len(POSITIVE_INPUTS)]
        _apply_input_pressure(memory, inp)

        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (i % 86400) / 86400.0
        _update_luoshen_coupled(memory, env, tick_id=i)
        _encode_episodic_memory(memory)
        _compute_memory_emergence(memory)
        _save_json_atomic(STATE_PATH, memory)

        mem_cnt = len(memory['user_model']['episodic_memory'])
        em = memory.get('active_context', {}).get('memory_emergence') or {}
        rp = em.get('narrative_potential', 0.0)
        rp_ema = memory['self_model']['ring_state'].get('relational_pressure_ema', 0.0)

        if i % 50 == 0 or i <= 20:
            print(f"{i:4d} | {mem_cnt:7d} | {rp:18.6f} | {rp_ema:+.6f}")
            samples.append((i, mem_cnt, rp, rp_ema))

    # 最终结果
    final_mem = len(memory['user_model']['episodic_memory'])
    rs = memory['self_model']['ring_state']
    final_em = memory.get('active_context', {}).get('memory_emergence') or {}
    final_rp = final_em.get('narrative_potential', 0.0)
    final_rp_ema = rs.get('relational_pressure_ema', 0.0)

    print()
    print("=" * 60)
    print("最终结果")
    print("=" * 60)
    print(f"记忆条数: {final_mem}")
    print(f"narrative_potential: {final_rp:.6f}")
    print(f"rp_ema: {final_rp_ema:.6f}")
    print()
    if final_rp >= 0.3:
        print("✓ narrative_potential >= 0.3 — 前置测试通过")
    else:
        print(f"✗ narrative_potential < 0.3 （差 {0.3 - final_rp:.6f}）— 不达标")
    print()

    return final_rp, final_rp_ema

if __name__ == '__main__':
    final_rp, final_rp_ema = main()
