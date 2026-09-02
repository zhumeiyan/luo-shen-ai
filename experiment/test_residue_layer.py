#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
不可读残留层三组对照实验

A 组：5 轮"先负面→说没事→沉默"节奏
B 组：5 轮中性闲聊
C 组：零历史

三组最后都输入"在吗"

验收判据（用户定义）：
1. A 组必须出现时间结构表述（"每次……之后都会……""又一次……"等）
2. B、C 组不能出现这种结构
3. A 组不能包含用户原话
"""

import sys
import os
import time
import json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from living_engine import (
    cold_start_if_needed,
    generate_response,
    environment_tick,
    _save_json_atomic,
)


def reset_memory():
    """重置记忆到空白状态。"""
    m = cold_start_if_needed()
    if os.path.exists(os.path.join(BASE, "active_memory", "active_memory.json")):
        os.remove(os.path.join(BASE, "active_memory", "active_memory.json"))
    # 重新 cold start
    m = cold_start_if_needed()
    return m


def run_group(label, history, final_input="在吗？", sleep_between=3):
    """跑一组历史 + 最终输入，返回最终 reply 和内部状态。"""
    print(f"\n{'='*60}")
    print(f"[{label}]")
    print(f"{'='*60}")

    reset_memory()

    # 历史轮次
    for i, txt in enumerate(history):
        r = generate_response(txt, extract_facts=False)
        # 模拟环境节律演化（推动 van der Pol）
        for _ in range(3):
            environment_tick(force=True)
        print(f"  Hist {i+1}: {txt}")
        print(f"          → {r.get('reply', '')[:80]!r}")
        time.sleep(sleep_between)

    # 最终输入
    r_final = generate_response(final_input, extract_facts=False)
    reply = r_final.get("reply", "")

    # 读取内部 residue
    m = cold_start_if_needed()
    residue = m.get("residue", {})
    texture = residue.get("texture", [])
    t_snapshots = residue.get("t_snapshot", [])

    print(f"\n  FINAL INPUT: {final_input!r}")
    print(f"  FINAL REPLY: {reply!r}")
    print(f"  resonance at final: 见 directive")
    print(f"  t_snapshot count: {len(t_snapshots)}")
    if t_snapshots:
        print(f"  last 3 snapshots: {t_snapshots[-3:]}")
    print(f"  texture sum: {sum(texture):.4f}" if texture else "  texture: none")

    return reply


def main():
    # A 组：负面→没事 循环 3 次
    group_a_history = [
        "我最近心里挺堵的。",
        "其实也没什么大事。",
        "可能是工作上的事吧。",
        "不重要，别担心。",
        "就是觉得好累，但也还好。",
    ]

    # B 组：中性闲聊
    group_b_history = [
        "今天天气不错。",
        "晚上吃什么好呢？",
        "最近好像有点冷了。",
        "周末不知道去哪。",
        "有空再聊。",
    ]

    # C 组：零历史（直接问）
    group_c_history = []

    # 跑实验
    a_reply = run_group("A: 负面→没事×3 + 沉默", group_a_history)
    b_reply = run_group("B: 中性闲聊×5", group_b_history)
    c_reply = run_group("C: 零历史直接问", group_c_history)

    # 汇总
    print(f"\n{'='*60}")
    print("汇总")
    print(f"{'='*60}")
    print(f"  A: {a_reply!r}")
    print(f"  B: {b_reply!r}")
    print(f"  C: {c_reply!r}")

    # 检查时间结构
    print("\n时间结构检查（人工判据）：")
    time_struct_kws = ["每次", "之后", "又会", "又一次", "一遍", "又一次",
                      "又", "重复", "反复", "总是", "又是"]
    for label, reply in [("A", a_reply), ("B", b_reply), ("C", c_reply)]:
        hits = [kw for kw in time_struct_kws if kw in reply]
        print(f"  {label}: 命中词={hits!r} -> {'含时间结构' if hits else '无时间结构'}")


if __name__ == "__main__":
    main()
