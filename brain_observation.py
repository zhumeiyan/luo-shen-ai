#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_observation.py — 认知核心 vs 洛神的观测对比模块

只读不改：
1. observe_core_vs_loshen(core, memory, user_id) → core 状态与洛神状态层的相关性
2. observe_per_user(core, user_id) → 检查全局 state 是否有 per-user 分化

约束：
- 不修改 cognitive_core 内部状态
- 不修改洛神 memory 状态
- 所有输出交给调用者，决定写日志 vs 丢弃
"""

import numpy as np
import time
from typing import Dict, Any, Optional


# 认知核心的 6 行 → 洛神状态层的映射
# 行 0-3 有直接对应；行 4-5 (attention/drive) 洛神没有独立变量
ROW_INDEX_TO_STATE = {
    0: "energy",
    1: "pain",
    2: "warmth",
    3: "withdraw",
}
ROW_INDEX_TO_STATE_FULL = {
    0: "energy",
    1: "pain",
    2: "warmth",
    3: "withdraw",
    4: "attention",
    5: "drive",
}


def observe_core_vs_loshen(core, memory: Dict[str, Any], user_id: str = "primary") -> Dict[str, Any]:
    """
    对比认知核心的 6 行均值 vs 洛神的状态层。
    
    计算：
    - 四对对应维度 (energy/pain/warmth/withdraw) 的 Pearson 相关系数
    - 方向一致性比例（core 行方向 与 洛神对应维度变化方向 是否一致）
    
    返回：
    {
        "ts": float,
        "core_row_means": [6 floats],
        "loshen_states": {"energy", "pain", "warmth", "withdraw", "attention", "drive"},
        "correlation": float,  # Pearson r on 4 paired dims
        "direction_consistency": float,  # 0..1, ratio of matched directions
        "core_vec": [4 floats],  # rows 0-3
        "loshen_vec": [4 floats],  # energy/pain/warmth/withdraw
        "pairs": [{"core": float, "loshen": float, "core_state": str, "loshen_state": str}, ...],
    }
    """
    ts = time.time()
    frame = core.frames[-1]
    core_row_means = [float(np.mean(frame[r])) for r in range(6)]
    
    # 读洛神状态层
    climate = memory.get("internal_climate", {})
    self_model = memory.get("self_model", {})
    relations = memory.get("relations", {}).get(user_id, {})
    
    loshen_energy = float(climate.get("energy", 0.5))
    loshen_pain = float(self_model.get("internal_pain", 0.0))
    loshen_warmth = float(relations.get("relationship_warmth", 0.0))
    loshen_withdraw = float(self_model.get("withdraw_tendency", 0.0))
    
    loshen_states = {
        "energy": loshen_energy,
        "pain": loshen_pain,
        "warmth": loshen_warmth,
        "withdraw": loshen_withdraw,
        "attention": 0.0,
        "drive": 0.0,
    }
    
    # 配对：core rows 0-3 → loshen energy/pain/warmth/withdraw
    core_vec = [core_row_means[i] for i in range(4)]
    loshen_vec = [loshen_energy, loshen_pain, loshen_warmth, loshen_withdraw]
    state_names = ["energy", "pain", "warmth", "withdraw"]
    
    # Pearson 相关系数
    c = np.array(core_vec)
    l = np.array(loshen_vec)
    c_centered = c - np.mean(c)
    l_centered = l - np.mean(l)
    denom = np.sqrt(np.sum(c_centered ** 2) * np.sum(l_centered ** 2))
    correlation = float(np.sum(c_centered * l_centered) / denom) if denom > 1e-12 else 0.0
    
    # 方向一致性：核心行均值方向 vs 洛神对应值偏离其自身的"中性点"方向
    # energy 中性在 0.5，其他中性在 0.0
    neutral_points = [0.5, 0.0, 0.0, 0.0]
    matched = 0
    pairs = []
    for i in range(4):
        core_dir = core_vec[i] - 0.0  # core 行的中性是 0
        loshen_dir = loshen_vec[i] - neutral_points[i]
        core_sign = np.sign(core_dir) if abs(core_dir) > 1e-8 else 0
        loshen_sign = np.sign(loshen_dir) if abs(loshen_dir) > 1e-8 else 0
        
        if core_sign == loshen_sign:
            matched += 1
        
        pairs.append({
            "core_value": round(core_vec[i], 6),
            "loshen_value": round(loshen_vec[i], 6),
            "core_state": ROW_INDEX_TO_STATE[i],
            "loshen_state": state_names[i],
            "core_direction": int(core_sign),
            "loshen_direction": int(loshen_sign),
            "matched": core_sign == loshen_sign,
        })
    
    direction_consistency = matched / 4 if len(pairs) > 0 else 0.0
    
    return {
        "ts": round(ts, 3),
        "core_row_means": [round(v, 6) for v in core_row_means],
        "loshen_states": {k: round(v, 6) for k, v in loshen_states.items()},
        "correlation": round(correlation, 6),
        "direction_consistency": round(direction_consistency, 4),
        "core_vec": [round(v, 6) for v in core_vec],
        "loshen_vec": [round(v, 6) for v in loshen_vec],
        "pairs": pairs,
    }


def observe_per_user(core, user_id: str) -> Dict[str, Any]:
    """
    记录当前 user_id 下认知核心的状态快照。
    由于认知核心当前是全局 state，此函数只记录"谁在观察"，不改 core。
    
    返回包含 user_id 和当前 core 摘要的快照，
    供后续比较同一 user_id 多次观察之间是否有累积差异。
    """
    frame = core.frames[-1]
    row_means = [float(np.mean(frame[r])) for r in range(6)]
    
    return {
        "ts": round(time.time(), 3),
        "user_id": user_id,
        "tick": core.tick_count,
        "phase": core.phase,
        "core_row_means": [round(v, 6) for v in row_means],
        "core_mean": round(float(np.mean(frame)), 6),
        "core_std": round(float(np.std(frame)), 6),
        "core_abs_max": round(float(np.max(np.abs(frame))), 6),
        "is_global_state": True,  # 标记：当前是全局 state，不支持 per-user
    }


def format_observation(obs: Dict[str, Any]) -> str:
    """单行人类可读摘要（用于调试/日志）"""
    if obs.get("type") == "core_vs_loshen":
        return (
            f"core_vs_loshen: r={obs['correlation']:.3f}, "
            f"dir_match={obs['direction_consistency']:.0%}"
        )
    elif "user_id" in obs and "core_abs_max" in obs:
        return (
            f"per_user[{obs['user_id']}]: tick={obs['tick']} "
            f"abs_max={obs['core_abs_max']:.4f} mean={obs['core_mean']:.4f}"
        )
    return str(obs)
