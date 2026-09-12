#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
renderer.py — 渲染器

原则：
- LLM 只是可选渲染器（不是脑）
- 默认不用 LLM：纯文本模板
- 有 LLM 时增强输出自然度
- 不阻塞认知核心运行
"""

import json
import os
import time
from typing import Optional, Dict, Any

from cognitive_core import CognitiveCore, ROW_LABELS

# 默认不使用 LLM
LLM_ENABLED = os.environ.get("COGNITIVE_CORE_LLM", "0") == "1"


def render(core: CognitiveCore, use_llm: bool = LLM_ENABLED) -> str:
    """
    渲染认知状态为自然语言文本。
    
    参数：
        core：认知核心实例
        use_llm：是否使用 LLM 增强（默认否）
    
    返回：
        人类可读的状态描述文本
    """
    if use_llm:
        return _render_with_llm(core)
    else:
        return core.render()


def _render_template(core: CognitiveCore) -> str:
    """
    模板渲染（无需 LLM）。
    注意：core.render() 已经实现了基础模板，
    这个函数是更丰富的版本用于外部调用。
    """
    return core.render()


def _render_with_llm(core: CognitiveCore) -> str:
    """
    使用 LLM 增强渲染（可选）。
    
    需要环境变量 COGNITIVE_CORE_LLM=1 且 llm_interface 可用。
    失败时回退到模板渲染。
    """
    try:
        # 尝试导入 living_engine 的 LLM 接口
        from llm_interface import call_llm
    except ImportError:
        return core.render()

    frame = core.frames[-1]
    intent = core._last_intent or core.read_intent()
    
    # 构造 prompt
    prompt = f"""你是洛神的认知核心。你的任务是把下面的内部状态数据翻译为一句话的自然语言状态描述（不超过50字）。

状态数据：
- tick: {core.tick_count}
- phase: {core.phase}
- 意图能量: {intent['energy']}
- 方向: {intent['direction']}
- 活跃格: {', '.join(c['cell'] for c in intent['top_cells'][:3])}
- 行签名: {intent['row_signature']}

要求：不要编造具体事件，只描述当前内部状态的大方向。用第一人称。"""
    
    try:
        llm_reply = call_llm(
            system_prompt="你是洛神，描述自己当前的认知状态。",
            user_message=prompt,
            max_tokens=100,
        )
        if llm_reply and len(llm_reply) < 200:
            return f"[LLM渲染] {llm_reply}"
    except Exception:
        pass
    
    return core.render()


def render_diff(core: CognitiveCore) -> str:
    """渲染最近帧的变化。"""
    d = core.diff
    if d is None:
        return "[diff] 暂无数据（需要至少 2 个 tick）"
    
    lines = ["[认知核心变化 diff]"]
    for r, label in enumerate(ROW_LABELS):
        changes = " ".join(f"{d[r,c]:+.3f}" for c in range(6))
        mean_change = float(np.mean(np.abs(d[r]))) if 'np' in dir() else 0.0
        lines.append(f"  {label[:4]:4s} [{changes}] 活跃度={mean_change:.3f}")
    
    return "\n".join(lines)


# 为了让 diff 的渲染不依赖 np，需要导入
import numpy as np


def render_structure(core: CognitiveCore) -> str:
    """渲染内部结构快照。"""
    hs = core.hidden_structure
    lines = ["[内部结构]"]
    lines.append(f"  耦合非零项: {hs['coupling_nonzero']} / {6*6*6*6}")
    lines.append(f"  耦合总和: {hs['coupling_sum']}")
    lines.append(f"  吸引子均值: {hs['attractor_mean']}")
    lines.append(f"  吸引子离散: {hs['attractor_std']}")
    return "\n".join(lines)


if __name__ == "__main__":
    from cognitive_core import get_core
    core = get_core(seed=42)
    for _ in range(5):
        core.tick_step()
    
    print(render(core))
    print()
    print(render_diff(core))
    print()
    print(render_structure(core))
