#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_check.snapshot — 当前状态快照

读取洛神此刻的 internal_climate + self_model，返回结构化快照。
不做判断，只读数。
"""


def snapshot_state(memory):
    """
    读取当前状态快照。

    返回形如：
    {
        "energy": -0.47,
        "tension": 0.23,
        "emotion_intensity": 0.05,
        "memory_pressure": 0.0,
        "internal_pain": 0.0,
        "withdraw_tendency": 0.28,
        "timestamp": 1725097822.0
    }
    """
    import time

    climate = memory.get("internal_climate", {})
    self_model = memory.get("self_model", {})

    return {
        "energy": climate.get("energy", 0.5),
        "tension": climate.get("tension", 0.0),
        "emotion_intensity": climate.get("emotion_intensity", 0.0),
        "memory_pressure": climate.get("memory_pressure", 0.0),
        "internal_pain": self_model.get("internal_pain", 0.0),
        "withdraw_tendency": self_model.get("withdraw_tendency", 0.0),
        "timestamp": time.time(),
    }


def snapshot_relations(memory, user_id="primary"):
    """
    读取某个用户的关系状态快照。
    """
    rel = memory.get("relations", {}).get(user_id, {})
    return {
        "warmth": rel.get("relationship_warmth", 0.0),
        "total_turns": rel.get("total_turns", 0),
        "tone_avg": (
            rel.get("tone_sum", 0.0) / max(1, rel.get("total_turns", 0))
        ),
    }
