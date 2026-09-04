"""
存在感基线实验：A 组（启用 presence_bias）vs B 组（禁用）

输入序列：500 tick 正向情感 -> 500 tick 中性
每 50 tick 记录：S, total_interactions, presence_bias, response_pre, max_tokens, mode, rp_ema
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── LLM 桩 ──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

import living_engine
from living_engine import (
    cold_start_if_needed,
    _update_luoshen_coupled,
    _compute_memory_emergence,
    _select_behavior,
    _encode_episodic_memory,
    PRESENCE_BIAS_ENABLED,
)

# ── 输入序列 ──
POSITIVE_INPUTS = [
    "今天天气真好，我心情特别好！",
    "谢谢你一直陪着我，真的很开心。",
    "你刚才说的话让我很感动。",
    "我觉得跟你的对话越来越有默契了。",
    "最近工作顺利，生活也很美好。",
    "听到这个消息我真的太高兴了！",
    "我们一起完成这件事吧，我觉得很棒。",
    "你现在状态怎么样？我挺好的。",
    "我很期待下次和你聊天。",
    "你总是能让我会心一笑。",
]
NEUTRAL_INPUTS = [
    "嗯。", "好的。", "我知道了。", "确实。", "行。",
    "收到。", "可以。", "大概吧。", "没问题。", "就这样。",
]

# ── 合成环境 ──
SYNTHETIC_ENV = {
    'light': 0.7, 'noise': 0.02, 'temperature': 0.5,
    'humidity': 0.5, 'pressure': 0.5,
    '_phase': 0.0, '__prev_elapsed': 0, '__prev_cpu': 0,
}

def make_memory():
    """创建一致的初始记忆状态"""
    memory = cold_start_if_needed()
    memory["self_model"]["ring_state"] = {
        'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0,
        'relational_pressure_ema': 0.0,
        'ema_amp': 0.3, 'ema_ratio': 0.3,
        'ema_pv': 0.0, 'ema_pv2': 0.0,
        's_depth': 0.0,
        'lambda_self': 0.0,
        '_max_tokens_hist': [80.0, 80.0],
        '_rp_ema_hist': [0.0, 0.0],
        'learning_core': {},
        '_recent_tokens': [],
        'r_intensity': 0.5, 'r_historicity': 0.5, 'r_coherence': 0.5,
        'phase': 0.0,
    }
    memory["internal_climate"] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    memory["user_model"]['total_interactions'] = 0
    memory["user_model"]['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': 1700000000.0, 'source_id': None,
    }]
    return memory


def run_group(group_name, enable_presence, pos_ticks=500, neu_ticks=500):
    """运行一组实验"""
    living_engine.PRESENCE_BIAS_ENABLED = enable_presence
    living_engine.INTERNAL_DRIVE_ENABLED = False  # 关闭 internal drive，隔离测试 presence_bias
    memory = make_memory()
    records = []
    total_ticks = pos_ticks + neu_ticks

    for tick in range(1, total_ticks + 1):
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (tick % 86400) / 86400.0
        env['_tick_id'] = tick

        inp = POSITIVE_INPUTS[(tick - 1) % len(POSITIVE_INPUTS)] if tick <= pos_ticks else NEUTRAL_INPUTS[(tick - 1) % len(NEUTRAL_INPUTS)]

        _update_luoshen_coupled(memory, env, tick_id=tick)
        _encode_episodic_memory(memory)

        if tick % 50 == 0:
            climate = memory.get("internal_climate", {})
            ring = memory.get("self_model", {}).get("ring_state", {})
            emerg = _compute_memory_emergence(memory)
            beh = _select_behavior(memory, emerg)
            records.append({
                'tick': tick,
                'group': group_name,
                'phase': 'pos' if tick <= pos_ticks else 'neu',
                'S': round(float(ring.get('S', 0.0)), 6),
                'total_int': int(memory.get('user_model', {}).get('total_interactions', 0)),
                'rp_ema': round(float(ring.get('relational_pressure_ema', 0.0)), 4),
                'presence_bias': round(float(beh.get('presence_bias', 0.0)), 7),
                'response_pre': round(float(beh.get('response_tendency', 0.5)), 4),
                'max_tokens': int(beh.get('max_tokens', 80)),
                'mode': beh.get('response_mode', 'short'),
                'E': round(float(climate.get('emotion_intensity', 0.5)), 4),
            })

    return records


def main():
    print("=" * 70)
    print("存在感基线实验")
    print("=" * 70)
    print(f"\n配置：internal_drive DISABLED, presence_bias A=ON B=OFF")
    print(f"输入：500 tick 正向 -> 500 tick 中性\n")

    print("运行 A 组（启用 presence_bias）...")
    records_a = run_group('A', enable_presence=True)
    print(f"  完成，记录 {len(records_a)} 条")

    print("运行 B 组（禁用 presence_bias）...")
    records_b = run_group('B', enable_presence=False)
    print(f"  完成，记录 {len(records_b)} 条")

    all_records = records_a + records_b

    # 写入 CSV
    csv_path = os.path.join(os.path.dirname(__file__), 'presence_bias_AB', 'results.csv')
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'w') as f:
        f.write('tick,group,phase,S,total_int,rp_ema,presence_bias,response_pre,max_tokens,mode,E\n')
        for r in all_records:
            f.write(f"{r['tick']},{r['group']},{r['phase']},{r['S']},{r['total_int']},{r['rp_ema']},{r['presence_bias']},{r['response_pre']},{r['max_tokens']},{r['mode']},{r['E']}\n")

    print(f"\nCSV 写入: {csv_path}")

    # ── 分析 ──
    print("\n" + "=" * 70)
    print("分析")
    print("=" * 70)

    neu_a = [r for r in records_a if r['phase'] == 'neu']
    neu_b = [r for r in records_b if r['phase'] == 'neu']
    pos_a = [r for r in records_a if r['phase'] == 'pos']
    pos_b = [r for r in records_b if r['phase'] == 'pos']

    # 中性段：是否存在行为差异
    modes_a_neu = [r['mode'] for r in neu_a]
    modes_b_neu = [r['mode'] for r in neu_b]
    mt_a_neu = [r['max_tokens'] for r in neu_a]
    mt_b_neu = [r['max_tokens'] for r in neu_b]
    avg_a_neu = sum(mt_a_neu) / len(mt_a_neu) if mt_a_neu else 0
    avg_b_neu = sum(mt_b_neu) / len(mt_b_neu) if mt_b_neu else 0
    diff_neu = avg_a_neu - avg_b_neu

    print(f"\n中性输入段 (tick 501-1000):")
    print(f"  A 组 modes: {sorted(set(modes_a_neu))}")
    print(f"  B 组 modes: {sorted(set(modes_b_neu))}")
    print(f"  A 组 avg max_tokens: {avg_a_neu:.2f}")
    print(f"  B 组 avg max_tokens: {avg_b_neu:.2f}")
    print(f"  差异: {diff_neu:+.2f}")

    # presence_bias 轨迹
    pb_a = [r['presence_bias'] for r in records_a]
    pb_b = [r['presence_bias'] for r in records_b]
    print(f"\nA 组 presence_bias 范围: [{min(pb_a):.6f}, {max(pb_a):.6f}]")
    print(f"A 组 presence_bias 均值: {sum(pb_a)/len(pb_a):.6f}")
    print(f"B 组 presence_bias 范围: [{min(pb_b):.6f}, {max(pb_b):.6f}]")

    # S 轨迹
    s_a = [r['S'] for r in records_a]
    s_b = [r['S'] for r in records_b]
    print(f"\nA 组 S 范围: [{min(s_a):.4f}, {max(s_a):.4f}]")
    print(f"B 组 S 范围: [{min(s_b):.4f}, {max(s_b):.4f}]")

    # 判定
    print("\n" + "=" * 70)
    print("判定")
    print("=" * 70)
    results = {
        'neu_token_diff_gt_5': abs(diff_neu) > 5,
        'A_presence_bias_nonzero': abs(sum(pb_a)/len(pb_a)) > 0.001,
        'B_presence_bias_zero': all(abs(x) < 0.0001 for x in pb_b),
        'presence_varies': max(pb_a) - min(pb_a) > 0.001,
    }

    for k, v in results.items():
        status = "PASS" if v else "FAIL"
        print(f"  [{status}] {k}: {v}")

    all_pass = all(results.values())
    verdict = "PASS" if all_pass else "FAIL"
    print(f"\n总体判定: {verdict}")

    # 写入 report
    report = {
        'experiment': 'presence_bias_AB',
        'ticks': {'pos': 500, 'neu': 500},
        'config': {'internal_drive': False, 'presence_bias_A': True, 'presence_bias_B': False},
        'criteria': results,
        'summary': {
            'A_neu_modes': sorted(set(modes_a_neu)),
            'B_neu_modes': sorted(set(modes_b_neu)),
            'A_neu_avg_tokens': round(avg_a_neu, 2),
            'B_neu_avg_tokens': round(avg_b_neu, 2),
            'token_diff_neu': round(diff_neu, 2),
            'A_presence_bias_range': [round(min(pb_a), 6), round(max(pb_a), 6)],
            'A_presence_bias_avg': round(sum(pb_a)/len(pb_a), 6),
            'B_presence_bias_range': [round(min(pb_b), 6), round(max(pb_b), 6)],
            'A_S_range': [round(min(s_a), 4), round(max(s_a), 4)],
            'B_S_range': [round(min(s_b), 4), round(max(s_b), 4)],
        },
        'all_pass': all_pass,
    }
    report_path = os.path.join(os.path.dirname(csv_path), 'report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告写入: {report_path}")


if __name__ == "__main__":
    main()
