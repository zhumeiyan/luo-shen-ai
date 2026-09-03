#!/usr/bin/env python3
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证脚本：修复后正向输入 500 tick 的记忆积累与 narrative_potential。
每 50 tick 输出一行：tick、记忆条数、narrative_potential。
不变动任何生产代码或参数。
"""
import sys, os, time, json, math

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
)

POSITIVE_INPUTS = [
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

SYNTHETIC_ENV = {
    'light': 0.7, 'noise': 0.02, 'temperature': 0.5,
    'humidity': 0.5, 'pressure': 0.5,
    '_phase': 0.0, '__prev_elapsed': 0, '__prev_cpu': 0,
}

STATE_PATH = os.path.join(WORKSPACE, "experiment", "verify_mem.json")

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

    print("tick | mem_cnt | narrative_potential | rp_ema")
    print("----+---------+---------------------+--------")

    for i in range(1, 501):
        inp = POSITIVE_INPUTS[(i - 1) % len(POSITIVE_INPUTS)]

        # 1. pressure input
        _apply_input_pressure(memory, inp)

        # 2. tick dynamics
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (i % 86400) / 86400.0
        _update_luoshen_coupled(memory, env, tick_id=i)

        # 3. 编码情景记忆 (修复后新增)
        _encode_episodic_memory(memory)

        # 4. emergence
        _compute_memory_emergence(memory)

        _save_json_atomic(STATE_PATH, memory)

        mem_cnt = len(memory['user_model']['episodic_memory'])
        em = memory.get('active_context', {}).get('memory_emergence') or {}
        rp = em.get('narrative_potential', 0.0)
        rp_ema = memory['self_model']['ring_state'].get('relational_pressure_ema', 0.0)

        if i % 50 == 0 or i in (1, 2, 5, 10, 20):
            print(f"{i:4d} | {mem_cnt:7d} | {rp:18.6f} | {rp_ema:+.6f}")

    # 最终确认
    final_mem = len(memory['user_model']['episodic_memory'])
    rs = memory['self_model']['ring_state']
    final_em = memory.get('active_context', {}).get('memory_emergence') or {}
    final_rp = final_em.get('narrative_potential', 0.0)
    print()
    print("=== 最终结果 ===")
    print(f"记忆条数: {final_mem}")
    print(f"narrative_potential: {final_rp:.6f}")
    print(f"rp_ema: {rs.get('relational_pressure_ema', 0):.6f}")
    print()
    if final_mem >= 50:
        print("记忆正常积累: 达到 MAX_MEMORIES 上限")
    else:
        print(f"记忆积累: {final_mem} 条 (未达上限)")

    return final_mem, final_rp

if __name__ == '__main__':
    final_mem, final_rp = main()
