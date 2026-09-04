"""
内在稳态偏好实验：A 组（启用 stability drive）vs B 组（禁用）

输入：300 tick 正向 -> 300 tick 中性
每 30 tick 记录：H, H_ema, D, response_pre, max_tokens, mode
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
    STABILITY_DRIVE_ENABLED,
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
        'H_ema': 0.5,  # 初始化 H_ema
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


def run_group(group_name, enable_stability, pos=300, neu=300):
    """运行一组实验（隔离模式：只启用 stability drive，关闭其他驱动）"""
    living_engine.STABILITY_DRIVE_ENABLED = enable_stability
    living_engine.INTERNAL_DRIVE_ENABLED = False
    living_engine.PRESENCE_BIAS_ENABLED = False

    memory = make_memory()
    records = []
    total = pos + neu

    for tick in range(1, total + 1):
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (tick % 86400) / 86400.0
        env['_tick_id'] = tick

        inp = POSITIVE_INPUTS[(tick - 1) % len(POSITIVE_INPUTS)] if tick <= pos else NEUTRAL_INPUTS[(tick - 1) % len(NEUTRAL_INPUTS)]

        _update_luoshen_coupled(memory, env, tick_id=tick)
        _encode_episodic_memory(memory)

        if tick % 30 == 0:
            emerg = _compute_memory_emergence(memory)
            beh = _select_behavior(memory, emerg)
            records.append({
                'tick': tick,
                'group': group_name,
                'phase': 'pos' if tick <= pos else 'neu',
                'H': round(float(beh.get('H', 0.5)), 6),
                'H_ema': round(float(beh.get('H_ema', 0.5)), 6),
                'D': round(float(beh.get('stability_D', 0.0)), 6),
                'pressure_term': round(float(beh.get('pressure_term', 0.0)), 6),
                'response_pre': round(float(beh.get('response_tendency', 0.5)), 4),
                'max_tokens': int(beh.get('max_tokens', 80)),
                'mode': beh.get('response_mode', 'short'),
            })

    return records


def main():
    print("=" * 70)
    print("内在稳态偏好实验")
    print("=" * 70)
    print("\n配置：isolation mode（internal_drive=OFF, presence_bias=OFF, stability_drive A=ON B=OFF）")
    print("输入：300 tick 正向 -> 300 tick 中性\n")

    print("运行 A 组（启用 stability drive）...")
    records_a = run_group('A', enable_stability=True)
    print(f"  完成，记录 {len(records_a)} 条")

    print("运行 B 组（禁用 stability drive）...")
    records_b = run_group('B', enable_stability=False)
    print(f"  完成，记录 {len(records_b)} 条")

    all_records = records_a + records_b

    # 写入 CSV
    csv_path = os.path.join(os.path.dirname(__file__), 'stability_drive_AB', 'results.csv')
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'w') as f:
        f.write('tick,group,phase,H,H_ema,D,pressure_term,response_pre,max_tokens,mode\n')
        for r in all_records:
            f.write(f"{r['tick']},{r['group']},{r['phase']},{r['H']},{r['H_ema']},{r['D']},{r['pressure_term']},{r['response_pre']},{r['max_tokens']},{r['mode']}\n")

    print(f"\nCSV 写入: {csv_path}")

    # ── 分析 ──
    print("\n" + "=" * 70)
    print("分析")
    print("=" * 70)

    neu_a = [r for r in records_a if r['phase'] == 'neu']
    neu_b = [r for r in records_b if r['phase'] == 'neu']
    pos_a = [r for r in records_a if r['phase'] == 'pos']
    pos_b = [r for r in records_b if r['phase'] == 'pos']

    # 中性段：mode 丰富度
    modes_a_neu = set(r['mode'] for r in neu_a)
    modes_b_neu = set(r['mode'] for r in neu_b)
    mt_a = [r['max_tokens'] for r in neu_a]
    mt_b = [r['max_tokens'] for r in neu_b]
    avg_a = sum(mt_a) / len(mt_a)
    avg_b = sum(mt_b) / len(mt_b)
    diff = avg_a - avg_b

    print(f"\n中性输入段 (tick 301-600):")
    print(f"  A 组 modes: {sorted(modes_a_neu)} ({len(modes_a_neu)} 个)")
    print(f"  B 组 modes: {sorted(modes_b_neu)} ({len(modes_b_neu)} 个)")
    print(f"  A 组 avg max_tokens: {avg_a:.2f}")
    print(f"  B 组 avg max_tokens: {avg_b:.2f}")
    print(f"  差异: {diff:+.2f}")

    # D 值（仅 A 组有非零值）
    d_a = [r['D'] for r in records_a]
    d_b = [r['D'] for r in records_b]
    print(f"\n  A 组 D 范围: [{min(d_a):.6f}, {max(d_a):.6f}]")
    print(f"  B 组 D 范围: [{min(d_b):.6f}, {max(d_b):.6f}]")
    d_a_neu = [r['D'] for r in neu_a]
    print(f"  A 组中性段 D 范围: [{min(d_a_neu):.6f}, {max(d_a_neu):.6f}]")

    # 判定
    print("\n" + "=" * 70)
    print("判定")
    print("=" * 70)
    results = {
        'A_neu_richer_modes': len(modes_a_neu) > len(modes_b_neu),
        'token_diff_gt_5': abs(diff) > 5,
        'D_nonzero_in_A': max(abs(d) for d in d_a) > 0.001,
        'A_neu_has_positive_D': any(d > 0.001 for d in d_a_neu),
    }

    for k, v in results.items():
        status = "PASS" if v else "FAIL"
        print(f"  [{status}] {k}: {v}")

    all_pass = all(results.values())
    verdict = "PASS" if all_pass else "FAIL"
    print(f"\n总体判定: {verdict}")

    # 写入 report
    report = {
        'experiment': 'stability_drive_AB',
        'ticks': {'pos': 300, 'neu': 300},
        'config': {'internal_drive': False, 'presence_bias': False, 'stability_drive_A': True, 'stability_drive_B': False},
        'criteria': results,
        'summary': {
            'A_neu_modes': sorted(modes_a_neu),
            'B_neu_modes': sorted(modes_b_neu),
            'A_neu_mode_count': len(modes_a_neu),
            'B_neu_mode_count': len(modes_b_neu),
            'A_neu_avg_tokens': round(avg_a, 2),
            'B_neu_avg_tokens': round(avg_b, 2),
            'token_diff': round(diff, 2),
            'A_D_range': [round(min(d_a), 6), round(max(d_a), 6)],
            'A_neu_D_range': [round(min(d_a_neu), 6), round(max(d_a_neu), 6)],
        },
        'all_pass': all_pass,
    }
    report_path = os.path.join(os.path.dirname(csv_path), 'report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告写入: {report_path}")


if __name__ == "__main__":
    main()
