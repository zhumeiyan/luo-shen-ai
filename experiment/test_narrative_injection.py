#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试浮现叙事层：验证洛神是否能说出"只能来自历史的话"。

链路：
1. 铺设 5 轮历史对话（围绕同一情感模式）
2. 每轮之间调用 environment_tick 模拟洛神内部气候自然演化
3. 第 6 轮问"在吗？"，检测 narrative_urgency 是否注入 + 洛神是否说出历史依赖的话
"""
import sys, os, time
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from living_engine import (
    cold_start_if_needed, generate_response,
    environment_tick, _save_json_atomic,
)

# ── 彻底重置 memory ──
def _reset():
    m =cold_start_if_needed()
    m['user_model']['episodic_memory'] = []
    m['user_model']['total_interactions'] = 0
    m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    _save_json_atomic('active_memory/active_memory.json', m)

# ── 历史对话（围绕一核心模式：否定自己的烦） ──
HISTORY = [
    ('我最近特别烦，但又说不清楚。', '高情感唤醒模式第1次出现'),
    ('其实也没什么事。',             '否定/最小化模式'),
    ('就是那种说不上来的烦。',       '高情感唤醒模式第2次出现'),
    ('我没事，别担心。',             '否定/最小化模式'),
    ('不知道，不想说了。',           '否定/最小化模式'),
]

def _read_narrative_potential():
    m = cold_start_if_needed()
    em = m.get('active_context', {}).get('memory_emergence')
    if em:
        return em.get('narrative_potential', 0.0)
    return 0.0


def main():
    _reset()

    print("===== 浮现叙事层测试 =====\n")
    print("5 轮历史 + 每轮之间的环境节律演化\n")

    for i, (user_text, note) in enumerate(HISTORY, 1):
        r = generate_response(user_text, extract_facts=False)
        reply = r.get('reply', '')
        print(f"[第 {i} 轮] {note}")
        print(f"  用户: {user_text}")
        print(f"  洛神: {reply[:80]}")

        # 模拟洛神在无人时节的内部演化（推动 van der Pol 极限环）
        # 每轮间隔 ~30 秒真实时间 → 强制 3 次 tick
        for _ in range(3):
            environment_tick(force=True)
        time.sleep(3)  # 给 API 冷却时间，避免限流

        np_val = _read_narrative_potential()
        print(f"  narrative_potential = {np_val:.4f}")
        print()

    # ── 第 6 轮：挑战句 ──
    print("=" * 50)
    print("[第 6 轮] 用户问：在吗？")
    r6 = generate_response('在吗？', extract_facts=False)
    reply6 = r6.get('reply', '')
    print(f"用户: 在吗？")
    print(f"洛神: {reply6}")
    print(f"完整 reply: {repr(r6.get('reply'))}")

    # ── 检查 narrative_urgency 注入 ──
    # 注入发生在 directive["context_for_llm"]["narrative_urgency"]
    # 但 generate_response 的返回值里不包含 directive。
    # 所以我们从 memory 里读取最后一次 emergence 来判断
    np_final = _read_narrative_potential()
    m_final = cold_start_if_needed()
    em_final = m_final.get('active_context', {}).get('memory_emergence', {})
    print(f"\n注入前 narrative_potential = {np_final:.4f}")
    if em_final:
        print(f"frame_weights = {em_final.get('narrative_frame_weights')}")
        print(f"hints = {em_final.get('narrative_hints')}")

    # ── 输出最终 reply ──
    print("\n===== 测试结论 =====")
    print(f"第 6 轮洛神回复: {repr(reply6)}")
    print(f"回复长度: {len(reply6)} 字")


if __name__ == '__main__':
    main()
