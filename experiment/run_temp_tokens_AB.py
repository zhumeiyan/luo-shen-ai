#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内部状态 → LLM 采样参数映射实验

温度/tokens 由 tone_bias/length_bias 连续映射，
跑 3 次看差异是否稳定。
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


def run_single_experiment(round_num, label, input_text):
    print(f"\n--- 第{round_num}轮 | {label} ---")
    cold_start_clean()

    # 第一次输入
    r1 = generate_response(input_text, source="experiment", extract_facts=False)
    print(f"  [输入1] {input_text}")
    print(f"  [回复1] {repr(r1.get('reply'))}")

    # 读取第一次后的 internal_climate
    with open(os.path.join(WORKSPACE, "active_memory", "active_memory.json"), "r") as f:
        mem = json.load(f)
    e_s = mem.get("user_model", {}).get("episodic_memory", [{}])[-1].get("e_s")
    print(f"  [e_s] {e_s}")

    time.sleep(2)

    # 第二次输入："在吗？"
    r2 = generate_response("在吗？", source="experiment", extract_facts=False)

    # 读取采样参数
    constraints = r2.get("directive", {}).get("constraints", {}) if r2.get("directive") else {}
    temperature = constraints.get("temperature", "?")
    max_tokens = constraints.get("max_tokens", "?")
    tone_bias = r2.get("emergence", {}).get("tone_bias", "?")
    length_bias = r2.get("emergence", {}).get("length_bias", "?")

    print(f"  [在吗？] {repr(r2.get('reply'))}")
    print(f"  tone_bias={tone_bias:.4f}, length_bias={length_bias:.4f}")
    print(f"  temperature={temperature:.4f}, max_tokens={max_tokens}")
    return {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tone_bias": tone_bias,
        "length_bias": length_bias,
        "reply": r2.get("reply"),
        "e_s": e_s,
    }


def main():
    print("=" * 60)
    print("采样参数映射 A/B 实验 × 3 轮")
    print("=" * 60)

    input_A = "我下个月要离开这座城市，其实我有点害怕。"
    input_B = "今天天气真好。"

    results = {"A": [], "B": []}
    for i in range(1, 4):
        print(f"\n{'='*60}")
        print(f"第 {i}/3 轮")
        print(f"{'='*60}")
        results["A"].append(run_single_experiment(i, "A (害怕)", input_A))
        results["B"].append(run_single_experiment(i, "B (天气)", input_B))

    # 汇总
    print(f"\n{'='*60}")
    print("3 轮汇总")
    print(f"{'='*60}")

    for label in ["A", "B"]:
        print(f"\n--- {label} ---")
        for i, r in enumerate(results[label], 1):
            reply_len = len(r["reply"]) if r["reply"] else 0
            print(f"  轮{i}: temp={r['temperature']:.4f}, max_tok={r['max_tokens']}, reply_len={reply_len}, reply={repr(r['reply'][:30])}...")

    # 计算差异稳定性
    A_temps = [r["temperature"] for r in results["A"]]
    B_temps = [r["temperature"] for r in results["B"]]
    A_toks = [r["max_tokens"] for r in results["A"]]
    B_toks = [r["max_tokens"] for r in results["B"]]
    A_lens = [len(r["reply"]) if r["reply"] else 0 for r in results["A"]]
    B_lens = [len(r["reply"]) if r["reply"] else 0 for r in results["B"]]

    print(f"\n差异汇总:")
    print(f"  temperature 差异: {[f'{a-b:.4f}' for a,b in zip(A_temps, B_temps)]}")
    print(f"  max_tokens 差异: {[a-b for a,b in zip(A_toks, B_toks)]}")
    print(f"  回复长度 A: {A_lens}")
    print(f"  回复长度 B: {B_lens}")

    # 稳定性判断
    temp_diffs = [a-b for a,b in zip(A_temps, B_temps)]
    tok_diffs = [a-b for a,b in zip(A_toks, B_toks)]
    len_diffs = [a-b for a,b in zip(A_lens, B_lens)]

    temp_consistent = all(d < 0 for d in temp_diffs)
    tok_consistent = all(d < 0 for d in tok_diffs)
    len_consistent = all(d < 0 for d in len_diffs)

    print(f"\n判断:")
    print(f"  temperature: A>B 恒成立? {temp_consistent} (差值: {temp_diffs})")
    print(f"  max_tokens:  A>B 恒成立? {tok_consistent} (差值: {tok_diffs})")
    print(f"  回复长度:    A>B 恒成立? {len_consistent} (差值: {len_diffs})")


if __name__ == "__main__":
    main()
