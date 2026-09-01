#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
输入压力通道 A/B 实验

直接验证：user input 是否让 internal_climate 产生结构性差异。
清空 known_facts，只用情感压力通道。
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
    """清空活记忆层，从零开始"""
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
        },
        "self_model": {
            "emotion": {"primary": "平静", "intensity": 0.5},
            "self_stated_state": {"last_stated": None, "last_stated_at": 0},
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


def read_climate():
    """读取当前 internal_climate"""
    memory_path = os.path.join(WORKSPACE, "active_memory", "active_memory.json")
    with open(memory_path, "r", encoding="utf-8") as f:
        memory = json.load(f)
    return memory.get("internal_climate", {})


def read_input_pressure():
    """读取当前存储的 input_pressure"""
    memory_path = os.path.join(WORKSPACE, "active_memory", "active_memory.json")
    with open(memory_path, "r", encoding="utf-8") as f:
        memory = json.load(f)
    return memory.get("active_context", {}).get("input_pressure")


def read_emergence():
    memory_path = os.path.join(WORKSPACE, "active_memory", "active_memory.json")
    with open(memory_path, "r", encoding="utf-8") as f:
        memory = json.load(f)
    return memory.get("active_context", {}).get("memory_emergence")


def run_single_experiment(label, input_text, call_llm=True):
    """跑一轮实验：说话 → 读气压 → 读气候 → 编码记忆 → 读 emergence"""
    print(f"\n{'='*60}")
    print(f"实验 {label}")
    print(f"{'='*60}")
    cold_start_clean()

    print(f"\n[输入] {input_text}")
    t0 = time.time()
    r = generate_response(input_text, source="experiment")
    t1 = time.time()

    print(f"  耗时: {t1-t0:.1f}s")
    if call_llm:
        print(f"  回复: {repr(r.get('reply', '(无)'))}")

    # 读取情感压力
    ip = read_input_pressure()
    if ip:
        print(f"  input_pressure: valence={ip.get('valence')}, arousal={ip.get('arousal')}")

    # 读取气候
    climate = read_climate()
    print(f"  climate: E={climate.get('emotion_intensity')}, T={climate.get('tension')}, N={climate.get('energy')}, M={climate.get('memory_pressure')}")

    # 读取一条记忆点的 e_s
    memory_path = os.path.join(WORKSPACE, "active_memory", "active_memory.json")
    with open(memory_path, "r", encoding="utf-8") as f:
        memory = json.load(f)
    episodic = memory.get("user_model", {}).get("episodic_memory", [])
    if episodic:
        last_mem = episodic[-1]
        print(f"  编码记忆点: e_s={last_mem.get('e_s')}, t_s={last_mem.get('t_s')}, n_s={last_mem.get('n_s')}")

    return {
        "label": label,
        "climate": climate,
        "input_pressure": ip,
        "episodic_count": len(episodic),
    }


def main():
    print("=" * 60)
    print("输入压力通道 A/B 实验")
    print("known_facts: 已清空")
    print("=" * 60)

    # A: 负向高唤醒
    result_A = run_single_experiment(
        "A: 负向高唤醒",
        "我下个月要离开这座城市，其实我有点害怕。"
    )

    # B: 中性低唤醒
    result_B = run_single_experiment(
        "B: 中性低唤醒",
        "今天天气真好。"
    )

    # 对比
    print(f"\n{'='*60}")
    print("差异对比")
    print(f"{'='*60}")

    ca = result_A["climate"]
    cb = result_B["climate"]

    print(f"\n{'指标':<15} {'A (负向)':<12} {'B (中性)':<12} {'差值 A-B':<12}")
    print(f"{'-'*50}")
    for key in ["emotion_intensity", "tension", "energy", "memory_pressure"]:
        va = ca.get(key, 0)
        vb = cb.get(key, 0)
        diff = va - vb
        label_map = {
            "emotion_intensity": "E",
            "tension": "T",
            "energy": "N",
            "memory_pressure": "M",
        }
        print(f"{label_map.get(key, key):<15} {va:<12.5f} {vb:<12.5f} {diff:<+12.5f}")

    # 输入压力对比
    ipa = result_A.get("input_pressure", {}) or {}
    ipb = result_B.get("input_pressure", {}) or {}
    print(f"\n情感压力:")
    print(f"  A: valence={ipa.get('valence')}, arousal={ipa.get('arousal')}")
    print(f"  B: valence={ipb.get('valence')}, arousal={ipb.get('arousal')}")


if __name__ == "__main__":
    main()
