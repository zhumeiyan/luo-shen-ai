#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
50 轮连续交互数据采集 — A/B 双组平行跑。

输出 CSV 字段：
  turn, group, relational_awareness, self_awareness_signal, max_tokens, pressure_memory_mod, rp_ema

注意：本环境为沙箱，llm_interface.call_llm 已 patch 为空字符串桩，
因此 response_tokens 实为 behavior 层决定的 max_tokens 上限。
真实 LLM 环境下，实际生成 token 数会围绕此值浮动。
"""
import sys, os, math, csv, statistics, time

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# ── Patch LLM（沙箱环境无 API）──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Patch 情感分析 ──
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
    _apply_input_pressure, _load_json, _save_json_atomic,
    cold_start_if_needed, _compute_memory_emergence, _select_behavior,
    idle_update_memory,
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
    """模拟 environment_tick 的核心逻辑"""
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

    # self_awareness_signal
    _ra = memory.get("self_model", {}).get("relational_awareness", 0.0)
    _sas = math.tanh(_ra * 1.5)
    memory["self_model"]["self_awareness_signal"] = round(_sas, 7)

    climate["emotion_intensity"] = max(0.0, min(1.0, E + (0.5 - E) * 0.001))
    climate["tension"] = max(-1.0, min(1.0, T * 0.999))
    memory["internal_climate"] = climate


def compute_emergence_in_memory(memory):
    _compute_memory_emergence(memory)


def run_group(group_label, inputs, n_turns=50):
    """跑单组 n_turns 轮交互，返回 CSV 行列表"""
    reset_memory()
    memory = _load_json(MEMORY_PATH)

    rows = []
    for turn in range(1, n_turns + 1):
        user_input = inputs[(turn - 1) % len(inputs)]

        # 1. 用户输入 → 压力积累
        apply_in_memory(memory, user_input)

        # 2. 环境 tick（重建 ring_state + self_awareness_signal）
        tick_in_memory(memory)

        # 3. 计算浮现层（写入 relational_awareness + pressure_memory_mod）
        compute_emergence_in_memory(memory)

        # 4. 行为选择（决定 max_tokens）
        emergence = memory.get('active_context', {}).get('memory_emergence')
        if emergence:
            behavior = _select_behavior(memory, emergence)
            max_tokens = behavior.get('max_tokens', 0)
        else:
            max_tokens = 0

        # 5. 采集状态量
        rs = memory.get('self_model', {}).get('ring_state', {})
        ra = memory.get('self_model', {}).get('relational_awareness', None)
        sas = memory.get('self_model', {}).get('self_awareness_signal', None)
        pmm = memory.get('active_context', {}).get('memory_emergence', {}).get('pressure_memory_mod', None) if emergence else None
        rpe = rs.get('relational_pressure_ema', None)

        rows.append({
            'turn': turn,
            'group': group_label,
            'relational_awareness': ra,
            'self_awareness_signal': sas,
            'max_tokens': max_tokens,
            'pressure_memory_mod': pmm,
            'rp_ema': rpe,
        })

    _save_json_atomic(MEMORY_PATH, memory)
    return rows


def main():
    print(f"{'='*90}")
    print("50 轮连续交互数据采集")
    print(f"{'='*90}")

    t0 = time.time()
    print("\n[A 组] 负向输入 × 50 轮...")
    rows_a = run_group("A", NEG_INPUTS, 50)
    print("[B 组] 正向输入 × 50 轮...")
    rows_b = run_group("B", POS_INPUTS, 50)
    elapsed = time.time() - t0

    # ── 写入 CSV ──
    output_path = 'experiment/AB_50turns_data.csv'
    fieldnames = ['turn', 'group', 'relational_awareness', 'self_awareness_signal',
                  'max_tokens', 'pressure_memory_mod', 'rp_ema']
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_a)
        writer.writerows(rows_b)

    # ── 汇报摘要 ──
    print(f"\n{'='*90}")
    print("数据采集完成")
    print(f"{'='*90}")
    print(f"\n输出文件: {output_path}")
    print(f"总行数: {len(rows_a) + len(rows_b)} (A: {len(rows_a)}, B: {len(rows_b)})")
    print(f"执行时间: {elapsed:.2f} 秒")

    # 摘要统计
    for label, rows in [("A", rows_a), ("B", rows_b)]:
        ra_vals = [r['relational_awareness'] for r in rows if isinstance(r['relational_awareness'], (int, float))]
        sas_vals = [r['self_awareness_signal'] for r in rows if isinstance(r['self_awareness_signal'], (int, float))]
        tok_vals = [r['max_tokens'] for r in rows if isinstance(r['max_tokens'], int)]
        pmm_vals = [r['pressure_memory_mod'] for r in rows if isinstance(r['pressure_memory_mod'], (int, float))]

        print(f"\n  {label} 组:")
        if ra_vals:
            print(f"    relational_awareness: 均值={statistics.mean(ra_vals):+.5f}, 范围=[{min(ra_vals):+.5f}, {max(ra_vals):+.5f}]")
        if sas_vals:
            print(f"    self_awareness_signal: 均值={statistics.mean(sas_vals):+.5f}, 范围=[{min(sas_vals):+.5f}, {max(sas_vals):+.5f}]")
        if tok_vals:
            print(f"    max_tokens:           均值={statistics.mean(tok_vals):.1f}, 范围=[{min(tok_vals)}, {max(tok_vals)}]")
        if pmm_vals:
            print(f"    pressure_memory_mod:  均值={statistics.mean(pmm_vals):.5f}, 范围=[{min(pmm_vals):.5f}, {max(pmm_vals):.5f}]")

    # 前 10 行预览
    print(f"\n前 10 行预览（A 组）:")
    print(f"{'turn':>4} | {'ra':>10} | {'sas':>9} | {'tok':>5} | {'pmm':>7} | {'rpe':>10}")
    print("-" * 60)
    for r in rows_a[:10]:
        ra_s = f"{r['relational_awareness']:>+10.5f}" if isinstance(r['relational_awareness'], (int, float)) else f"{'MISS':>10}"
        sas_s = f"{r['self_awareness_signal']:>+9.4f}" if isinstance(r['self_awareness_signal'], (int, float)) else f"{'MISS':>9}"
        pmm_s = f"{r['pressure_memory_mod']:>7.4f}" if isinstance(r['pressure_memory_mod'], (int, float)) else f"{'N/A':>7}"
        rpe_s = f"{r['rp_ema']:>+10.5f}" if isinstance(r['rp_ema'], (int, float)) else f"{'MISS':>10}"
        print(f"{r['turn']:4d} | {ra_s} | {sas_s} | {r['max_tokens']:>5} | {pmm_s} | {rpe_s}")

    print(f"\n前 10 行预览（B 组）:")
    print(f"{'turn':>4} | {'ra':>10} | {'sas':>9} | {'tok':>5} | {'pmm':>7} | {'rpe':>10}")
    print("-" * 60)
    for r in rows_b[:10]:
        ra_s = f"{r['relational_awareness']:>+10.5f}" if isinstance(r['relational_awareness'], (int, float)) else f"{'MISS':>10}"
        sas_s = f"{r['self_awareness_signal']:>+9.4f}" if isinstance(r['self_awareness_signal'], (int, float)) else f"{'MISS':>9}"
        pmm_s = f"{r['pressure_memory_mod']:>7.4f}" if isinstance(r['pressure_memory_mod'], (int, float)) else f"{'N/A':>7}"
        rpe_s = f"{r['rp_ema']:>+10.5f}" if isinstance(r['rp_ema'], (int, float)) else f"{'MISS':>10}"
        print(f"{r['turn']:4d} | {ra_s} | {sas_s} | {r['max_tokens']:>5} | {pmm_s} | {rpe_s}")

    # 临界点检查
    print(f"\n{'='*90}")
    print("临界点检查")
    print(f"{'='*90}")
    for label, rows in [("A", rows_a), ("B", rows_b)]:
        ra_vals = [r for r in rows if isinstance(r['relational_awareness'], (int, float))]
        min_ra = min(ra_vals, key=lambda x: x['relational_awareness'])
        max_ra = max(ra_vals, key=lambda x: x['relational_awareness'])
        print(f"  {label}: min_ra={min_ra['relational_awareness']:+.5f} (turn {min_ra['turn']}), max_ra={max_ra['relational_awareness']:+.5f} (turn {max_ra['turn']})")
        if label == "A" and min_ra['relational_awareness'] < -0.5:
            print(f"    ⚠ A 组已跌破 -0.5 阈值 (turn {min_ra['turn']})")
        if label == "A" and min_ra['relational_awareness'] >= -0.5:
            print(f"    ✓ A 组未跌破 -0.5 (最低 {min_ra['relational_awareness']:+.5f})")
        if label == "B" and max_ra['relational_awareness'] > 0.5:
            print(f"    ✓ B 组已过 +0.5 阈值 (turn {max_ra['turn']})")

    print(f"\n{'='*90}")
    print("CSV 就绪，上传即切入分析")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()
