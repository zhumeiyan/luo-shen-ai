#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
稳定性验证：5 轮 A/B 实验
每轮从头开始，检查内部状态到行为差异的链路是否稳定
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


def read_memory():
    with open(os.path.join(WORKSPACE, "active_memory", "active_memory.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def run_5rounds():
    input_A = "我下个月要离开这座城市，其实我有点害怕。"
    input_B = "今天天气真好。"

    records = {"A": [], "B": []}

    for i in range(5):
        print(f"\n{'='*60}")
        print(f"第 {i+1}/5 轮")
        print(f"{'='*60}")

        for label, inp in [("A", input_A), ("B", input_B)]:
            cold_start_clean()
            r1 = generate_response(inp, source="experiment", extract_facts=False)
            time.sleep(1.5)
            r2 = generate_response("在吗？", source="experiment", extract_facts=False)

            mem = read_memory()
            episodic = mem.get("user_model", {}).get("episodic_memory", [])
            last_mem = episodic[-1] if episodic else {}

            behavior = r2.get("behavior", {})
            emergence = r2.get("emergence", {})

            record = {
                "e_s": last_mem.get("e_s"),
                "t_s": last_mem.get("t_s"),
                "e_bg": emergence.get("background", {}).get("e_bg"),
                "tone_bias": emergence.get("tone_bias"),
                "length_bias": emergence.get("length_bias"),
                "resp_tendency": behavior.get("response_tendency"),
                "response_mode": behavior.get("response_mode"),
                "length_level": behavior.get("length_level"),
                "tone_mode_idx": behavior.get("tone_mode_idx"),
                "reply": r2.get("reply"),
                "reply_len": len(r2.get("reply", "")) if r2.get("reply") else 0,
                "llm_called": r2.get("llm_called"),
            }
            records[label].append(record)

            print(f"\n{label}: e_s={record['e_s']:.4f}, e_bg={record['e_bg']:.4f}")
            print(f"   tone_bias={record['tone_bias']:.4f}, length_bias={record['length_bias']:.4f}")
            print(f"   resp_tend={record['resp_tendency']:.4f}, mode={record['response_mode']}, len_lev={record['length_level']}, tone_idx={record['tone_mode_idx']}")
            print(f"   reply({record['reply_len']}字): {repr(record['reply'][:50])}...")

    # 汇总分析
    print(f"\n{'='*60}")
    print("5 轮汇总")
    print(f"{'='*60}")

    print(f"\n{'轮次':<4} {'A_e_s':<8} {'B_e_s':<8} {'Δe_s':<8} {'A_resp':<8} {'B_resp':<8} {'Δresp':<8} {'A_mode':<8} {'B_mode':<8}")
    for i in range(5):
        a = records["A"][i]
        b = records["B"][i]
        delta_e = a["e_s"] - b["e_s"]
        delta_r = a["resp_tendency"] - b["resp_tendency"]
        print(f"{i+1:<4} {a['e_s']:<8.4f} {b['e_s']:<8.4f} {delta_e:<+8.4f} {a['resp_tendency']:<8.4f} {b['resp_tendency']:<8.4f} {delta_r:<+8.4f} {a['response_mode']:<8} {b['response_mode']:<8}")

    # 稳定性统计
    delta_es = [r["e_s"] for r in records["A"]]
    delta_eb = [r["e_s"] for r in records["B"]]
    delta_resp_a = [r["resp_tendency"] for r in records["A"]]
    delta_resp_b = [r["resp_tendency"] for r in records["B"]]
    delta_mode_a = [r["response_mode"] for r in records["A"]]
    delta_mode_b = [r["response_mode"] for r in records["B"]]
    delta_len = [r["reply_len"] for r in records["A"]]
    delta_len_b = [r["reply_len"] for r in records["B"]]

    print(f"\n稳定性分析:")
    print(f"  e_s 差异: A-B = {[f'{a-b:+.4f}' for a,b in zip(delta_es, delta_eb)]}")
    print(f"  resp_tendency: A-B = {[f'{a-b:+.4f}' for a,b in zip(delta_resp_a, delta_resp_b)]}")
    print(f"  回复长度差 A-B: {[f'{a-b:+d}' for a,b in zip(delta_len, delta_len_b)]}")
    print(f"  A 行为模式: {delta_mode_a}")
    print(f"  B 行为模式: {delta_mode_b}")

    # 一致性判断
    e_diff_consistent = all(abs(a-b) > 0.03 for a,b in zip(delta_es, delta_eb))
    resp_consistent = all(abs(a-b) > 0.02 for a,b in zip(delta_resp_a, delta_resp_b))
    mode_a_stable = len(set(delta_mode_a)) <= 2
    mode_b_stable = len(set(delta_mode_b)) <= 2

    print(f"\n一致性:")
    print(f"  e_s 差异 > 0.03 持续? {e_diff_consistent}")
    print(f"  resp 差异 > 0.02 持续? {resp_consistent}")
    print(f"  A 行为模式稳定（≤2种）? {mode_a_stable}")
    print(f"  B 行为模式稳定（≤2种）? {mode_b_stable}")


if __name__ == "__main__":
    run_5rounds()
