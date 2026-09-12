#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persistence.py — 洛神认知核心持久化层

原则：
- 保存/加载认知核心状态到磁盘
- 原子写入（写临时文件再 rename）
- 不丢失滚动帧历史
- 只有 NumPy 标准库依赖

文件：cognitive_core_state.npz（二进制）+ cognitive_core_meta.json（可读元信息）
"""

import json
import os
import time
import numpy as np
from typing import Optional, Dict, Any

from cognitive_core import CognitiveCore

STATE_FILE = "cognitive_core_state.npz"
META_FILE = "cognitive_core_meta.json"


def save_core(core: CognitiveCore, state_file: str = STATE_FILE, meta_file: str = META_FILE) -> Dict[str, Any]:
    """
    保存核心状态。原子写入。
    
    返回元信息字典。
    """
    # 先写临时文件再 rename（原子替换）
    tmp_state = state_file + ".tmp"
    tmp_meta = meta_file + ".tmp"

    np.savez_compressed(
        tmp_state,
        frames=core.frames,
        coupling=core.coupling,
        attractors=core.attractors,
    )
    
    meta = {
        "tick_count": core.tick_count,
        "phase": core.phase,
        "phase_history": core.phase_history,
        "timestamp": time.time(),
        "grid_shape": list(core.frames.shape),
    }
    
    with open(tmp_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 原子替换
    os.replace(tmp_state, state_file)
    os.replace(tmp_meta, meta_file)

    return meta


def load_core(core: CognitiveCore, state_file: str = STATE_FILE, meta_file: str = META_FILE) -> Optional[Dict[str, Any]]:
    """
    从磁盘加载状态到现有核心对象。
    
    返回元信息字典，如果文件不存在返回 None。
    """
    if not os.path.exists(state_file) or not os.path.exists(meta_file):
        return None

    data = np.load(state_file)
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    core.frames = data["frames"]
    core.coupling = data["coupling"]
    core.attractors = data["attractors"]
    core.tick_count = meta["tick_count"]
    core.phase = meta["phase"]
    core.phase_history = meta.get("phase_history", [])

    return meta


def save_if_needed(core: CognitiveCore, every_n_ticks: int = 10) -> Optional[Dict[str, Any]]:
    """每 N 个 tick 保存一次（如果尚未保存）。"""
    if core.tick_count % every_n_ticks == 0:
        return save_core(core)
    return None


if __name__ == "__main__":
    from cognitive_core import get_core
    core = get_core(seed=42)
    for _ in range(5):
        core.tick_step()
    meta = save_core(core)
    print(f"已保存: tick={meta['tick_count']}, phase={meta['phase']}")
    
    core2 = get_core(seed=99)
    loaded_meta = load_core(core2)
    print(f"已加载: tick={loaded_meta['tick_count']}, phase={loaded_meta['phase']}")
    print(f"帧形状: {core2.frames.shape}")
