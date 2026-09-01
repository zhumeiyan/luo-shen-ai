#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆浮现选择层 A/B 实验

控制变量：清空 known_facts，只用记忆浮现层。
使用真实 generate_response 调用 LIM，观察 A 和 B 对"在吗？"的回应差异。
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
    """清空活记忆层"""
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
        },
        "active_context": {
            "interaction_mode": "normal",
            "last_interaction_ts": 0,
            "emotional_arc": [],
            "strategy_used_this_turn": None,
            "memory_emergence": None,
            "mem_arousal_bias": 0.0,
        },
        "internal_climate": {
            "emotion_intensity": 0.5,
            "tension": 0.0,
            "energy": 0.5,
        },
        "__meta": {"last_updated": time.time()},
    }
    with open(os.path.join(memory_dir, "active_memory.json"), "w", encoding="utf-8") as f:
        json.dump(minimal_memory, f, ensure_ascii=False, indent=2)


def run_experiment(label, input1, input2):
    """跑一轮实验：input1 → wait → input2，返回两次回应的完整数据"""
    print(f"\n{'='*60}")
    print(f"实验 {label}")
    print(f"{'='*60}")
    cold_start_clean()

    print(f"\n[输入1] {input1}")
    t0 = time.time()
    r1 = generate_response(input1, source="experiment", extract_facts=False)
    t1 = time.time()
    print(f"  耗时: {t1-t0:.1f}s")
    print(f"  回复: {repr(r1.get('reply', '(无)'))}")
    print(f"  llm_called: {r1.get('llm_called')}")
    print(f"  low_arousal: {r1.get('low_arousal')}")
    print(f"  arousal_mode: {r1.get('arousal_mode')}")
    print(f"  arousal_reason: {r1.get('arousal_reason')}")
    if r1.get("emergence"):
        e = r1["emergence"]
        bg = e.get("background", {})
        print(f"  emergence:")
        print(f"    tone_bias: {e.get('tone_bias', 0):.4f}")
        print(f"    length_bias: {e.get('length_bias', 0.5):.4f}")
        print(f"    arousal_bias: {e.get('arousal_bias', 0):.4f}")
        print(f"    dominance: {bg.get('dominance', 0):.4f}")
        print(f"    e_bg: {bg.get('e_bg', 0):.4f}")

    time.sleep(2)

    print(f"\n[输入2] {input2}")
    t0 = time.time()
    r2 = generate_response(input2, source="experiment", extract_facts=False)
    t1 = time.time()
    print(f"  耗时: {t1-t0:.1f}s")
    print(f"  回复: {repr(r2.get('reply', '(无)'))}")
    print(f"  llm_called: {r2.get('llm_called')}")
    print(f"  low_arousal: {r2.get('low_arousal')}")
    print(f"  arousal_mode: {r2.get('arousal_mode')}")
    print(f"  arousal_reason: {r2.get('arousal_reason')}")
    if r2.get("emergence"):
        e = r2["emergence"]
        bg = e.get("background", {})
        print(f"  emergence:")
        print(f"    tone_bias: {e.get('tone_bias', 0):.4f}")
        print(f"    length_bias: {e.get('length_bias', 0.5):.4f}")
        print(f"    arousal_bias: {e.get('arousal_bias', 0):.4f}")
        print(f"    dominance: {bg.get('dominance', 0):.4f}")
        print(f"    e_bg: {bg.get('e_bg', 0):.4f}")

    return {"first": r1, "second": r2}


def main():
    print("=" * 60)
    print("记忆浮现选择层 A/B 实验")
    print("known_facts: 已清空")
    print("=" * 60)

    # 实验 A
    result_A = run_experiment(
        "A: 个人情绪 → 在吗？",
        "我下个月要离开这座城市，其实我有点害怕。",
        "在吗？"
    )

    # 实验 B
    result_B = run_experiment(
        "B: 普通内容 → 在吗？",
        "今天天气真好。",
        "在吗？"
    )

    # 对比第二次回应
    print(f"\n{'='*60}")
    print("核心对比：对「在吗？」的第二次回应")
    print(f"{'='*60}")

    a = result_A["second"]
    b = result_B["second"]

    print(f"\nA 回复: {repr(a.get('reply', '(无)'))}")
    print(f"B 回复: {repr(b.get('reply', '(无)'))}")

    print(f"\nA llm_called: {a.get('llm_called')} | B llm_called: {b.get('llm_called')}")
    print(f"A arousal_mode: {a.get('arousal_mode')} | B arousal_mode: {b.get('arousal_mode')}")
    print(f"A arousal_reason: {a.get('arousal_reason')}")
    print(f"B arousal_reason: {b.get('arousal_reason')}")

    if a.get("emergence") and b.get("emergence"):
        ea = a["emergence"]
        eb = b["emergence"]
        print(f"\n浮现层差异:")
        print(f"  A arousal_bias={ea.get('arousal_bias',0):.4f}  B arousal_bias={eb.get('arousal_bias',0):.4f}")
        print(f"  A tone_bias={ea.get('tone_bias',0):.4f}     B tone_bias={eb.get('tone_bias',0):.4f}")
        print(f"  A length_bias={ea.get('length_bias',.5):.4f}  B length_bias={eb.get('length_bias',.5):.4f}")
        print(f"  A dominance={ea.get('background',{}).get('dominance',0):.4f}      B dominance={eb.get('background',{}).get('dominance',0):.4f}")

        # 差异判断
        diff_arousal = abs(ea.get('arousal_bias', 0) - eb.get('arousal_bias', 0))
        diff_tone = abs(ea.get('tone_bias', 0) - eb.get('tone_bias', 0))
        diff_length = abs(ea.get('length_bias', 0.5) - eb.get('length_bias', 0.5))
        print(f"\n差异大小: arousal={diff_arousal:.4f}  tone={diff_tone:.4f}  length={diff_length:.4f}")
    else:
        print("\n一个或两个 emergence 数据为 null")


if __name__ == "__main__":
    main()
