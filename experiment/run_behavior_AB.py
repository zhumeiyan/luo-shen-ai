#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行为选择层 A/B 实验 × 3 轮
"""

import os
import sys
import json
import time

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORKSPACE)
sys.path.insert(0, WORKSPACE)

from living_engine import generate_response


def cold_start_clean():
    memory_dir = os.path.join(WORKSPACE, "active_memory")
    os.makedirs(memory_dir, exist_ok=True)
    minimal_memory = {
        "user_model": {
            "known_facts": {"facts": [], "last_update": 0},
            "episodic_memory": [],
            "total_interactions": 0,
            "shared_history_length": 0,
            "intimacy": {"value": 0.5},
            "emotional_patterns": [],
            "preferences": [],
        },
        "self_model": {
            "emotion": {"primary": "平静", "intensity": 0.5},
            "self_stated_state": {"last_stated": None, "last_stated_at": None},
            "strategy_weights": {},
            "ring_state": {"E": 0.5, "T": 0.0, "N": 0.5, "M": 0.3},
        },
        "active_context": {
            "interaction_mode": "normal",
            "last_interaction_ts": 0,
            "emotional_arc": [],
            "strategy_used_this_turn": None,
            "memory_emergence": None,
            "input_pressure": None,
            "mem_arousal_bias": 0.0,
        },
        "internal_climate": {
            "emotion_intensity": 0.5,
            "tension": 0.0,
            "energy": 0.5,
            "memory_pressure": 0.3,
        },
        "__meta": {"last_updated": time.time()},
    }
    with open(os.path.join(memory_dir, "active_memory.json"), "w", encoding="utf-8") as f:
        json.dump(minimal_memory, f, ensure_ascii=False, indent=2)


def run_round(round_num, label, input1):
    print(f"\n--- 第{round_num}轮 | {label} ---")
    cold_start_clean()

    r1 = generate_response(input1, source="experiment", extract_facts=False)
    print(f"  [输入1] {input1}")
    print(f"  [回复1] {repr(r1.get('reply'))}")

    time.sleep(2)

    r2 = generate_response("在吗？", source="experiment", extract_facts=False)

    behavior = r2.get("behavior", {})
    emergence = r2.get("emergence", {})
    constraints = r2.get("directive", {}).get("constraints", {}) if r2.get("directive") else {}

    print(f"  [在吗？] {repr(r2.get('reply'))}")
    print(f"  behavior: mode={behavior.get('response_mode')}, len_level={behavior.get('length_level')}, tone_idx={behavior.get('tone_mode_idx')}, resp_tend={behavior.get('response_tendency')}")
    print(f"  LLM: temp={constraints.get('temperature', '?'):.3f}, max_tokens={constraints.get('max_tokens', '?')}")
    print(f"  llm_called={r2.get('llm_called')}, reply_len={len(r2.get('reply', ''))}")

    return {
        "behavior": behavior,
        "constraints": constraints,
        "reply": r2.get("reply"),
        "llm_called": r2.get("llm_called"),
    }


def main():
    print("=" * 60)
    print("行为选择层 A/B 实验 × 3 轮")
    print("=" * 60)

    input_A = "我下个月要离开这座城市，其实我有点害怕。"
    input_B = "今天天气真好。"

    results_A = []
    results_B = []

    for i in range(1, 4):
        print(f"\n{'='*60}")
        print(f"第 {i}/3 轮")
        print(f"{'='*60}")
        results_A.append(run_round(i, "A (害怕)", input_A))
        results_B.append(run_round(i, "B (天气)", input_B))

    # 汇总
    print(f"\n{'='*60}")
    print("行为参数对比")
    print(f"{'='*60}")

    for i in range(3):
        a = results_A[i]["behavior"]
        b = results_B[i]["behavior"]
        print(f"\n轮{i+1}:")
        print(f"  A: mode={a['response_mode']}, len={a['length_level']}, tone={a['tone_mode_idx']}, resp={a['response_tendency']}")
        print(f"  B: mode={b['response_mode']}, len={b['length_level']}, tone={b['tone_mode_idx']}, resp={b['response_tendency']}")
        same = (a["response_mode"] == b["response_mode"] and
                a["length_level"] == b["length_level"] and
                a["tone_mode_idx"] == b["tone_mode_idx"])
        print(f"  行为参数相同? {same}")

    # 回复长度对比
    print(f"\n回复长度:")
    for i in range(3):
        a_len = len(results_A[i]["reply"]) if results_A[i]["reply"] else 0
        b_len = len(results_B[i]["reply"]) if results_B[i]["reply"] else 0
        print(f"  轮{i+1}: A={a_len}, B={b_len}, 差={a_len - b_len}")


if __name__ == "__main__":
    main()
