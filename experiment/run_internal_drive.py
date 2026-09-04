"""
内部节律驱动实验：A 组（启用 _internal_drive）vs B 组（禁用）

输入序列：500 tick 正向情感 -> 50 tick 中性
记录每 10 tick：E, T, N, M, rp_ema, max_tokens, mode, response_pre, internal_drive
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── LLM 桩 ──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

import living_engine
from living_engine import (
    cold_start_if_needed,
    _save_json_atomic,
    _update_luoshen_coupled,
    _compute_memory_emergence,
    _select_behavior,
    _encode_episodic_memory,
    INTERNAL_DRIVE_ENABLED,
)
import input_pressure

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
    "嗯。",
    "好的。",
    "我知道了。",
    "确实。",
    "行。",
    "收到。",
    "可以。",
    "大概吧。",
    "没问题。",
    "就这样。",
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


def run_group(group_name, enable_drive, pos_ticks=500, neu_ticks=50):
    """运行一组实验"""
    living_engine.INTERNAL_DRIVE_ENABLED = enable_drive
    memory = make_memory()
    records = []
    total_ticks = pos_ticks + neu_ticks

    for tick in range(1, total_ticks + 1):
        # 构建环境
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (tick % 86400) / 86400.0
        env['_tick_id'] = tick

        # 选择输入
        if tick <= pos_ticks:
            inp = POSITIVE_INPUTS[(tick - 1) % len(POSITIVE_INPUTS)]
        else:
            inp = NEUTRAL_INPUTS[(tick - 1) % len(NEUTRAL_INPUTS)]

        # 简化处理：只调用 _update_luoshen_coupled（不经过 input_pressure 完整流水线，否则 rp_ema 等会被外部主导）
        _update_luoshen_coupled(memory, env, tick_id=tick)
        _encode_episodic_memory(memory)

        # 记录
        if tick % 10 == 0 or tick == 1:
            climate = memory.get("internal_climate", {})
            ring = memory.get("self_model", {}).get("ring_state", {})
            emerg = _compute_memory_emergence(memory)
            beh = _select_behavior(memory, emerg)
            records.append({
                'tick': tick,
                'group': group_name,
                'phase': 'pos' if tick <= pos_ticks else 'neu',
                'E': round(float(climate.get('emotion_intensity', 0.5)), 4),
                'T': round(float(climate.get('tension', 0.0)), 4),
                'N': round(float(climate.get('energy', 0.5)), 4),
                'M': round(float(climate.get('memory_pressure', 0.3)), 4),
                'rp_ema': round(float(ring.get('relational_pressure_ema', 0.0)), 4),
                's_depth': round(float(ring.get('s_depth', 0.0)), 4),
                'max_tokens': int(beh.get('max_tokens', 80)),
                'mode': beh.get('response_mode', 'short'),
                'response_pre': round(float(beh.get('response_tendency', 0.5)), 4),
                'internal_drive': round(float(beh.get('internal_drive', 0.0)), 6),
                'pressure_term': round(float(beh.get('pressure_term', 0.0)), 6),
            })

    return records


def main():
    print("=" * 70)
    print("内部节律驱动实验")
    print("=" * 70)

    # A 组：启用 internal drive
    print("\n运行 A 组（启用 _internal_drive）...")
    records_a = run_group('A', enable_drive=True)
    print(f"  完成，记录 {len(records_a)} 条")

    # B 组：禁用 internal drive
    print("\n运行 B 组（禁用 _internal_drive）...")
    records_b = run_group('B', enable_drive=False)
    print(f"  完成，记录 {len(records_b)} 条")

    all_records = records_a + records_b

    # 写入 CSV
    csv_path = os.path.join(os.path.dirname(__file__), 'internal_drive_AB', 'results.csv')
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'w') as f:
        header = 'tick,group,phase,E,T,N,M,rp_ema,s_depth,max_tokens,mode,response_pre,internal_drive,pressure_term'
        f.write(header + '\n')
        for r in all_records:
            f.write(f"{r['tick']},{r['group']},{r['phase']},{r['E']},{r['T']},{r['N']},{r['M']},{r['rp_ema']},{r['s_depth']},{r['max_tokens']},{r['mode']},{r['response_pre']},{r['internal_drive']},{r['pressure_term']}\n")

    print(f"\nCSV 写入: {csv_path}")

    # ── 分析 ──
    print("\n" + "=" * 70)
    print("分析")
    print("=" * 70)

    # 正向输入段（tick <= 500）
    pos_a = [r for r in records_a if r['phase'] == 'pos']
    pos_b = [r for r in records_b if r['phase'] == 'pos']
    neu_a = [r for r in records_a if r['phase'] == 'neu']
    neu_b = [r for r in records_b if r['phase'] == 'neu']

    # mode 多样性
    modes_a = set(r['mode'] for r in pos_a)
    modes_b = set(r['mode'] for r in pos_b)
    print(f"\n正向输入段（500 tick, 每 10 tick 采样）:")
    print(f"  A 组 modes: {sorted(modes_a)}")
    print(f"  B 组 modes: {sorted(modes_b)}")

    # max_tokens 差异
    mt_a = [r['max_tokens'] for r in pos_a]
    mt_b = [r['max_tokens'] for r in pos_b]
    avg_a, avg_b = sum(mt_a)/len(mt_a), sum(mt_b)/len(mt_b)
    diff_pos = avg_a - avg_b
    print(f"  A 组 avg max_tokens: {avg_a:.2f}")
    print(f"  B 组 avg max_tokens: {avg_b:.2f}")
    print(f"  差异: {diff_pos:+.2f}")

    # internal_drive 均值
    id_a = [r['internal_drive'] for r in pos_a]
    id_b = [r['internal_drive'] for r in pos_b]
    print(f"  A 组 avg internal_drive: {sum(id_a)/len(id_a):.6f}")
    print(f"  B 组 avg internal_drive: {sum(id_b)/len(id_b):.6f}")

    # 中性输入段（50 tick）
    nmt_a = [r['max_tokens'] for r in neu_a]
    nmt_b = [r['max_tokens'] for r in neu_b]
    navg = sum(nmt_a)/len(nmt_a) if nmt_a else 0
    nbavg = sum(nmt_b)/len(nmt_b) if nmt_b else 0
    diff_neu = navg - nbavg
    nids_a = set(r['mode'] for r in neu_a)
    nids_b = set(r['mode'] for r in neu_b)
    print(f"\n中性输入段（50 tick, 每 10 tick 采样）:")
    print(f"  A 组 modes: {sorted(nids_a)}")
    print(f"  B 组 modes: {sorted(nids_b)}")
    print(f"  A 组 avg max_tokens: {navg:.2f}")
    print(f"  B 组 avg max_tokens: {nbavg:.2f}")
    print(f"  差异: {diff_neu:+.2f}")

    # 判定
    print("\n" + "=" * 70)
    print("判定")
    print("=" * 70)
    results = {
        'pos_mode_diff': len(modes_a) > len(modes_b),
        'pos_token_diff_gt_5': abs(diff_pos) > 5,
        'neu_mode_diff': len(nids_a) != len(nids_b) or nids_a != nids_b,
        'neu_token_diff': abs(diff_neu),
        'A_internal_drive_nonzero': abs(sum(id_a)/len(id_a)) > 0.01,
        'B_internal_drive_zero': abs(sum(id_b)/len(id_b)) < 0.001,
    }

    for k, v in results.items():
        status = "PASS" if v else "FAIL"
        print(f"  [{status}] {k}: {v}")

    all_pass = all(results.values())
    verdict = "PASS" if all_pass else "FAIL"
    print(f"\n总体判定: {verdict}")

    # 写入 report
    report = {
        'experiment': 'internal_drive_AB',
        'ticks': {'pos': 500, 'neu': 50},
        'criteria': results,
        'summary': {
            'A_modes_pos': sorted(modes_a),
            'B_modes_pos': sorted(modes_b),
            'A_avg_tokens_pos': round(avg_a, 2),
            'B_avg_tokens_pos': round(avg_b, 2),
            'A_avg_tokens_neu': round(navg, 2),
            'B_avg_tokens_neu': round(nbavg, 2),
            'token_diff_pos': round(diff_pos, 2),
            'token_diff_neu': round(diff_neu, 2),
            'A_avg_internal_drive': round(sum(id_a)/len(id_a), 6),
            'B_avg_internal_drive': round(sum(id_b)/len(id_b), 6),
        },
        'all_pass': all_pass,
    }
    report_path = os.path.join(os.path.dirname(csv_path), 'report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告写入: {report_path}")


if __name__ == "__main__":
    main()
