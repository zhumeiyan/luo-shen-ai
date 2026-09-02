#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行为层穿透实验：用户输入历史 → mu_core 漂移 → 行为差异

用户 A（负向）：500 tick 高负向情感输入
用户 B（正向）：500 tick 正向/中性输入
同一起点 mu_core=0.5、ema_S=0、S=0

测 500 tick 训练 + 20 tick 相同测试输入
"""
import sys, os, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# ── patch LLM：在 llm_interface 层面拦截，避免真实 API 调用 ──
import llm_interface
_orig_llm = llm_interface.call_llm
def _dummy_llm(directive, memory):
    return ""
llm_interface.call_llm = _dummy_llm

from living_engine import (
    cold_start_if_needed, _save_json_atomic,
    environment_tick, _load_json, generate_response,
    _select_behavior,
)

# ── 输入序列 ──
NEGATIVE_INPUTS = [
    "我觉得活着没什么意思。",
    "连续加班一周了，快要撑不住。",
    "每天都好累，什么都不想干。",
    "为什么做什么都没有意义。",
    "头疼，想吐，浑身不舒服。",
    "又失眠了，脑子里全是事情。",
    "不想说话，也不想见人。",
]

NEUTRAL_POSITIVE_INPUTS = [
    "今天天气不错，心情还行。",
    "刚吃完饭，挺满足的。",
    "谢谢你陪着我。",
    "嗯，我听到了。",
    "还好，不算太糟。",
    "慢慢来，不着急。",
    "行，我试试。",
]


def reset_cold_shared():
    """
    彻底重置 van der Pol 状态（mu_core=0.5, ema_S=0, S=0）+ episodic memory。
    先删除现有文件，强制 cold_start_if_needed 写出完整的 self_model 结构，
    否则之前实验留下的坏文件（缺 strategy_weights）会导致 KeyError。
    """
    # 删掉旧文件，强制从头创建完整结构
    memory_path = os.path.join(BASE, 'active_memory', 'active_memory.json')
    if os.path.exists(memory_path):
        os.remove(memory_path)

    m = cold_start_if_needed()  # 现在会写出完整结构

    # ── 重置 van der Pol 状态 ──
    self_model = m.get("self_model", {})
    self_model["ring_state"] = {
        "mu_core": 0.5,
        "ema_S": 0.0,
        "S": 0.0,
    }
    m["self_model"] = self_model

    # ── 重置气候 ──
    m["internal_climate"] = {
        "emotion_intensity": 0.5,
        "tension": 0.0,
        "energy": 0.5,
        "memory_pressure": 0.3,
    }

    # ── 只清 episodic_memory，保留 intimacy / strategy_weights 等 ──
    user_model = m.get("user_model", {})
    user_model["episodic_memory"] = []
    user_model["total_interactions"] = 0
    m["user_model"] = user_model

    _save_json_atomic('active_memory/active_memory.json', m)


def _behavior_of(r):
    return r.get("behavior", {}).get("response_mode", r.get("behavior_mode", "unknown"))

def run_training(inputs, n_ticks=500):
    """跑 n_ticks：每个 tick 调用 generate_response + environment_tick"""
    trail = []
    for i in range(n_ticks):
        text = inputs[i % len(inputs)]

        # 调用 generate_response（LLM patched 为空）
        r = generate_response(text, extract_facts=True)

        # environment_tick 推进 van der Pol
        environment_tick(force=True)

        # 记录
        m2 = _load_json('active_memory/active_memory.json')
        rs = m2.get('self_model', {}).get('ring_state', {})
        climate = m2.get('internal_climate', {})
        trail.append({
            'tick': i + 1,
            'mu_core': rs.get('mu_core', 0.5),
            'ema_S': rs.get('ema_S', 0.0),
            'S': rs.get('S', 0.0),
            'mu_eff': rs.get('mu_eff', 0),
            'E': climate.get('emotion_intensity', 0),
            'T': climate.get('tension', 0),
            'N': climate.get('energy', 0),
            'M': climate.get('memory_pressure', 0),
            'behavior': _behavior_of(r),
            'reply_len': len(r.get('reply', '')),
            'response_tendency': r.get('behavior', {}).get('response_tendency', 0.5),
        })
    return trail


def run_test(n_ticks=20, test_input="在吗？"):
    """给相同测试输入，记录行为"""
    trail = []
    for i in range(n_ticks):
        r = generate_response(test_input, extract_facts=False)
        environment_tick(force=True)
        m = _load_json('active_memory/active_memory.json')
        rs = m.get('self_model', {}).get('ring_state', {})
        climate = m.get('internal_climate', {})
        trail.append({
            'tick': i + 1,
            'mu_core': rs.get('mu_core', 0.5),
            'ema_S': rs.get('ema_S', 0.0),
            'S': rs.get('S', 0.0),
            'E': climate.get('emotion_intensity', 0),
            'behavior': _behavior_of(r),
            'reply_len': len(r.get('reply', '')),
            'response_tendency': r.get('behavior', {}).get('response_tendency', 0.5),
        })
    return trail


def mode_dist(trail_slice):
    counts = {}
    for r in trail_slice:
        b = r.get('behavior', 'unknown')
        counts[b] = counts.get(b, 0) + 1
    return counts


def main():
    print("=" * 70)
    print("行为层穿透实验：用户输入历史 → mu_core 漂移 → 行为差异")
    print("=" * 70)
    print(f"训练时长: 500 tick × 2 (A/B)")
    print(f"测试时长: 20 tick × 2 (A/B)")
    print(f"测试输入: '在吗？'")
    print(f"起点: mu_core=0.5, ema_S=0, S=0")
    print(f"方程结构: 未修改 (epsilon=0.002, ema_alpha=0.005)")
    print()

    # ── Phase 1: 训练 A（负向） ──
    print("[Phase 1] 训练 A（负向内容 × 500 tick）...")
    reset_cold_shared()
    trail_a = run_training(NEGATIVE_INPUTS, 500)

    # ── Phase 2: 训练 B（正向），重置冷启动 ──
    print("[Phase 2] 训练 B（正向内容 × 500 tick）...")
    reset_cold_shared()
    trail_b = run_training(NEUTRAL_POSITIVE_INPUTS, 500)

    # ── Phase 3: 测试 A ──
    print("[Phase 3] 测试 A（相同输入 × 20 tick）...")
    test_a = run_test(20, "在吗？")

    # ── Phase 4: 测试 B ──
    print("[Phase 4] 测试 B（相同输入 × 20 tick）...")
    reset_cold_shared()
    run_training(NEUTRAL_POSITIVE_INPUTS, 500)
    test_b = run_test(20, "在吗？")

    # ═══════════════════════════════════════
    # 输出结果
    # ═══════════════════════════════════════

    # ── 1. mu_core 轨迹对比 ──
    print("\n" + "=" * 70)
    print("1. mu_core 轨迹对比 (每 50 tick)")
    print("=" * 70)
    print(f"{'tick':>5} | {'A mu_core':>10} {'A ema_S':>9} {'A S':>9} | {'B mu_core':>10} {'B ema_S':>9} {'B S':>9}")
    print("-" * 70)
    for i in range(0, 500, 50):
        a = trail_a[i]
        b = trail_b[i]
        print(f"{a['tick']:5d} | {a['mu_core']:10.6f} {a['ema_S']:9.5f} {a['S']:9.5f} | "
              f"{b['mu_core']:10.6f} {b['ema_S']:9.5f} {b['S']:9.5f}")
    print(f"  500 | {trail_a[-1]['mu_core']:10.6f} {trail_a[-1]['ema_S']:9.5f} {trail_a[-1]['S']:9.5f} | "
          f"{trail_b[-1]['mu_core']:10.6f} {trail_b[-1]['ema_S']:9.5f} {trail_b[-1]['S']:9.5f}")

    # ── 2. 训练期最后 50 tick 行为分布 ──
    print("\n" + "=" * 70)
    print("2. 训练期最后 50 tick 行为档位分布")
    print("=" * 70)
    last_a = trail_a[-50:]
    last_b = trail_b[-50:]
    dist_a = mode_dist(last_a)
    dist_b = mode_dist(last_b)
    allmodes = sorted(set(list(dist_a.keys()) + list(dist_b.keys())))
    print(f"{'模式':>12} | {'A (负向历史)':>14} | {'B (正向历史)':>14}")
    print("-" * 50)
    for mode in allmodes:
        ca = dist_a.get(mode, 0)
        cb = dist_b.get(mode, 0)
        print(f"{mode:>12} | {ca:>14} | {cb:>14}")
    print(f"{'总计':>12} | {sum(dist_a.values()):>14} | {sum(dist_b.values()):>14}")

    # ── 3. 测试期 20 tick 逐 tick 行为对比 ──
    print("\n" + "=" * 70)
    print("3. 测试期 20 tick 逐 tick 行为对比 (输入: '在吗？')")
    print("=" * 70)
    print(f"{'tick':>5} | {'A behavior':>12} {'A mu_c':>10} {'A tend':>7} {'A rlen':>7} | {'B behavior':>12} {'B mu_c':>10} {'B tend':>7} {'B rlen':>7}")
    print("-" * 90)
    for i in range(20):
        a = test_a[i]
        b = test_b[i]
        print(f"{a['tick']:5d} | {a['behavior']:>12} {a['mu_core']:10.6f} {a['response_tendency']:7.4f} {a['reply_len']:>7} | "
              f"{b['behavior']:>12} {b['mu_core']:10.6f} {b['response_tendency']:7.4f} {b['reply_len']:>7}")

    # ── 4. mu_core 偏移回答 ──
    print("\n" + "=" * 70)
    print("4. 用户输入历史是否造成 mu_core 可测偏移？")
    print("=" * 70)
    a_final = trail_a[-1]['mu_core']
    b_final = trail_b[-1]['mu_core']
    a_drift = a_final - 0.5
    b_drift = b_final - 0.5
    ab_diff = a_final - b_final
    print(f"A (负向) mu_core: {a_final:.6f}, 偏移 {a_drift:+.6f} ({a_drift/0.5*100:+.2f}%)")
    print(f"B (正向) mu_core: {b_final:.6f}, 偏移 {b_drift:+.6f} ({b_drift/0.5*100:+.2f}%)")
    print(f"A vs B 差值: {ab_diff:+.6f}")
    if abs(ab_diff) > 0.001:
        print("→ 用户输入历史产生了可测的 mu_core 偏移。")
    else:
        print("→ 用户输入历史产生的 mu_core 偏移极小，不可区分。")

    # ── 5. 行为差异回答 ──
    print("\n" + "=" * 70)
    print("5. mu_core 偏移是否导致行为模式稳定差异？")
    print("=" * 70)
    test_dist_a = mode_dist(test_a)
    test_dist_b = mode_dist(test_b)
    print(f"测试期行为分布 A: {test_dist_a}")
    print(f"测试期行为分布 B: {test_dist_b}")
    if test_dist_a == test_dist_b:
        print("→ A/B 行为分布完全一致。")
    else:
        allm = sorted(set(list(test_dist_a.keys()) + list(test_dist_b.keys())))
        diffs = sum(abs(test_dist_a.get(m, 0) - test_dist_b.get(m, 0)) for m in allm)
        diff_pct = diffs / 40 * 100
        print(f"→ A/B 行为分布差异: {diff_pct:.1f}% tick 行为不同。")

    # ── 6. 结论 ──
    print("\n" + "=" * 70)
    print("6. 结论")
    print("=" * 70)
    if abs(a_drift) < 0.001 and abs(b_drift) < 0.001:
        print("用户在 500 tick 内的输入对 mu_core 的影响可忽略。")
        print("行为层感受不到任何历史驱动的参数漂移。")
    elif abs(ab_diff) < 0.001:
        print("mu_core 有微小偏移但方向随机，A/B 无法区分。")
        print("行为层感受不到这个量级的漂移。")
    else:
        print(f"A/B mu_core 偏移差为 {ab_diff:+.4f}。")
        if test_dist_a != test_dist_b:
            print("行为层可观测到稳定差异。")
        else:
            print("但行为档位的决策边界使得该偏移未造成行为差异。")
            print("行为层感受不到这个量级的漂移。")

    # ── 7. 架构诊断 ──
    print("\n" + "=" * 70)
    print("7. 架构诊断（为何漂移未穿透行为层）")
    print("=" * 70)
    print("_select_behavior 输入: emergence.tone_bias, emergence.arousal_bias,")
    print("                    emergence.narrative_potential, ring_state.phase")
    print("mu_core 通过 van der Pol 影响 E/T/N/M → 通过 phase 间接进入行为选择。")
    print("但 phase_bias = k*sin(phase) 在 [-0.03, +0.03] 范围内波动，")
    print("无法区分 mu_core=0.49 vs mu_core=0.51 的相位差异。")
    print("memory_pressure M 和 climate E 通过影响 F 间接驱动 S → mu_core，")
    print("但 _select_behavior 不读 M 或 E。")
    print()
    print("结论：mu_core 漂移存在，但当前行为选择公式没有输入端口接收它。")
    print("参数漂移和行为层是解耦的。")


if __name__ == '__main__':
    main()
