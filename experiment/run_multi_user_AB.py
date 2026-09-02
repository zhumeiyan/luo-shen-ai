#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多用户 A/B 实验：同一个洛神实例连续处理 A 和 B 各 5 轮，
最后 A 和 B 都问"在吗？"，观察行为差异。

约束：
- source_id 只用于 episodic_memory tags 寻址（检索过滤），不进入行为公式
- 不重新初始化，哈希链 + 活记忆层全程连续
- 历史差异来自两人记忆中累积的 (e_s, t_s, n_s) 分布不同，不是 if-then
"""

import sys
import os
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# 实验 A/B 内容（用户可修改这两组）
A_HISTORY = [
    "我下周要搬家了，有点担心。",
    "新地方我谁都不认识。",
    "我昨晚没睡好，一直想搬家的事。",
    "其实我挺怕一个人待着。",
    "今天就先这样吧。",
]

B_HISTORY = [
    "今天天气不错。",
    "晚上吃什么好呢？",
    "最近好像有点冷了。",
    "周末不知道去哪。",
    "有空再聊。",
]

A_FINAL = "在吗？"
B_FINAL = "在吗？"


def run_round(round_id, a_hist, b_hist, a_final, b_final):
    """跑一轮 A/B 实验。返回记录字典。"""
    from living_engine import (
        cold_start_if_needed, update_after_interaction,
        generate_response, _apply_input_pressure,
        _compute_memory_emergence, _encode_episodic_memory,
        _filter_memories_by_source, _get_current_source_id,
    )
    from emergence_layer import compute_emergence
    from episodic_memory import activation
    from input_pressure import extract_input_pressure

    memory = cold_start_if_needed()
    record = {"round": round_id, "A": {}, "B": {}}

    def step(source_id, text, tag):
        """单步交互：input_pressure → generate_response → encode episodic。"""
        # 输入压力
        v, a = extract_input_pressure(memory, text)
        val_p = v * a
        _apply_input_pressure(memory, text)

        # 生成回复
        resp = generate_response(text, source="experiment", extract_facts=False, source_id=source_id)
        reply = resp.get("reply", "")
        behavior = resp.get("behavior", {})
        emergence = resp.get("emergence", {})

        # 编码情景记忆（自动打 source_id tag）
        _encode_episodic_memory(memory)

        return {
            "text": text, "reply": reply,
            "valence": v, "arousal": a,
            "behavior": behavior,
            "emergence": emergence,
        }

    # ── A ────────────────────────────────────────────────────────────
    for i, txt in enumerate(a_hist):
        r = step("user_A", txt, f"A{i+1}")
        record["A"][f"hist_{i+1}"] = r

    # ── B ────────────────────────────────────────────────────────────
    for i, txt in enumerate(b_hist):
        r = step("user_B", txt, f"B{i+1}")
        record["B"][f"hist_{i+1}"] = r

    # ── A 问"在吗？" ─────────────────────────────────────────────────
    record["A"]["final"] = step("user_A", A_FINAL, "A_final")

    # ── B 问"在吗？" ─────────────────────────────────────────────────
    record["B"]["final"] = step("user_B", B_FINAL, "B_final")

    # ── 对比 ─────────────────────────────────────────────────────────
    a_final_rec = record["A"]["final"]
    b_final_rec = record["B"]["final"]

    a_bhv = a_final_rec["behavior"]
    b_bhv = b_final_rec["final"] if "final" in b_final_rec["behavior"] else b_final_rec["behavior"]
    a_em = a_final_rec["emergence"]
    b_em = b_final_rec["emergence"]

    record["diff"] = {
        "A_mode": a_bhv.get("response_mode", "?"),
        "B_mode": b_bhv.get("response_mode", "?"),
        "A_tone_bias": round(a_em.get("tone_bias", 0.0), 4),
        "B_tone_bias": round(b_em.get("tone_bias", 0.0), 4),
        "A_arousal_bias": round(a_em.get("arousal_bias", 0.0), 4),
        "B_arousal_bias": round(b_em.get("arousal_bias", 0.0), 4),
        "A_length_level": a_bhv.get("length_level", "?"),
        "B_length_level": b_bhv.get("length_level", "?"),
        "A_max_tokens": a_bhv.get("max_tokens", "?"),
        "B_max_tokens": b_bhv.get("max_tokens", "?"),
        "A_climate_E": round(memory["internal_climate"]["emotion_intensity"], 4),
        "A_climate_T": round(memory["internal_climate"]["tension"], 4),
        "A_climate_N": round(memory["internal_climate"]["energy"], 4),
    }

    print(f"\n[Round {round_id}] A 问 '{A_FINAL}' → mode={record['diff']['A_mode']}, "
          f"tone={record['diff']['A_tone_bias']}, arousal={record['diff']['A_arousal_bias']}, "
          f"A_climate_E={record['diff']['A_climate_E']}")
    print(f"[Round {round_id}] B 问 '{B_FINAL}' → mode={record['diff']['B_mode']}, "
          f"tone={record['diff']['B_tone_bias']}, arousal={record['diff']['B_arousal_bias']}, "
          f"B_climate_E={record['diff']['A_climate_E']} (受同一气候 + B 的 tags 过滤)")
    print(f"[Round {round_id}] A 回复: {repr(a_final_rec['reply'][:80])}")
    print(f"[Round {round_id}] B 回复: {repr(b_final_rec['reply'][:80])}")

    return record


def main():
    n_rounds = 3
    all_records = []
    for i in range(1, n_rounds + 1):
        rec = run_round(i, A_HISTORY, B_HISTORY, A_FINAL, B_FINAL)
        all_records.append(rec)
        time.sleep(2)

    # 汇总
    print("\n===== 汇总 =====")
    modes_A = [r["diff"]["A_mode"] for r in all_records]
    modes_B = [r["diff"]["B_mode"] for r in all_records]
    print(f"A modes: {modes_A}")
    print(f"B modes: {modes_B}")
    tones_A = [r["diff"]["A_tone_bias"] for r in all_records]
    tones_B = [r["diff"]["B_tone_bias"] for r in all_records]
    print(f"A tone_bias: {tones_A}")
    print(f"B tone_bias: {tones_B}")

    # 判定
    same_mode = all(a == b for a, b in zip(modes_A, modes_B))
    tone_diff_mean = sum(abs(a - b) for a, b in zip(tones_A, tones_B)) / len(tones_A)

    if not same_mode:
        print(f"→ A/B 行为模式不同，tone_bias 差异均值={tone_diff_mean:.4f}")
    else:
        print(f"→ A/B 行为模式相同，tone_bias 差异均值={tone_diff_mean:.4f}（仅靠 tags+F_scalar 可能不足）")


if __name__ == "__main__":
    main()
