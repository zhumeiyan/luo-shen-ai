#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断洛神 extract_facts 管道：用户输入 → 事实提取 → episodic_memory 字段。

目的：回答一个关键问题：
  "洛神对'我很难过'和'我很开心'的 extract_facts 产出有什么差异？"

如果两者的产出相同（都只有文本切片，没有 valence/arousal 信号），
则用户输入历史无法驱动内部气候差异。

不调用 LLM，只检查洛神 logi 管道的内部步骤。
"""
import sys, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from living_engine import (
    cold_start_if_needed, _save_json_atomic, _load_json,
)

NEGATIVE_INPUT = "我觉得活着没什么意思，每天都很累，不想说话。"
POSITIVE_INPUT = "今天天气很好，心情不错，刚吃了一顿满足的午饭。"


def _inspect_memory(memory, label):
    """打印 memory 中与用户输入相关的关键字段。"""
    print(f"\n── {label} ──")
    # internal climate（van der Pol 更新前的旧值）
    climate = memory.get("internal_climate", {})
    print(f"  internal_climate: {climate}")

    # van der Pol ring_state
    rs = memory.get("self_model", {}).get("ring_state", {})
    print(f"  ring_state: {rs}")

    # user_model.episodic_memory 最后 2 条
    um = memory.get("user_model", {})
    em = um.get("episodic_memory", [])
    print(f"  episodic_memory 共 {len(em)} 条，最后 3 条：")
    for i, e in enumerate(em[-3:], 1):
        # 只打印关键字段，避免刷屏
        keys_to_show = ["timestamp", "fact_type", "content", "confidence",
                        "arousal", "valence", "sentiment", "pressure"]
        short = {k: e.get(k) for k in keys_to_show if k in e}
        print(f"    [{i}] {short}")

    # user_model 自身更新
    print(f"  user_model.trust: {um.get('trust')}")
    print(f"  user_model.intimacy: {um.get('intimacy')}")


def main():
    print("=" * 70)
    print("诊断 extract_facts 管道（无 LLM）")
    print("=" * 70)

    # ── 1. 冷启动 ──
    m = cold_start_if_needed()
    if 'internal_climate' not in m:
        m['internal_climate'] = {'emotion_intensity': 0.5, 'tension': 0.0, 'energy': 0.5, 'memory_pressure': 0.3}
    _save_json_atomic('active_memory/active_memory.json', m)
    baseline = _load_json('active_memory/active_memory.json')
    _inspect_memory(baseline, "冷启动后（基线）")

    print("\n" + "=" * 70)
    print("注意：洛神.extract_facts 的主流路径依赖 LLM 调用。")
    print("在无 LLM 的测试环境下，episodic_memory 不会被自动填充。")
    print("=" * 70)

    # ── 2. 查看 extract_facts 函数源码（直接 grep 不调用）──
    import inspect
    from living_engine import extract_facts, infer_user_state_fused
    src = inspect.getsource(extract_facts)
    # 只打印前 80 行
    lines = src.split("\n")[:80]
    print("\n── extract_facts 函数签名和顶部逻辑 ──")
    for line in lines[:30]:
        print(f"  {line}")

    print("\n── infer_user_state_fused 返回结构（文档字符串）──")
    src2 = inspect.getsource(infer_user_state_fused)
    lines2 = src2.split("\n")[:30]
    for line in lines2:
        print(f"  {line}")


if __name__ == '__main__':
    main()
