#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_check.behavior_log — 整体行为观测记录

记录洛神每一轮交互的完整可观测量：
- 状态层：E/T/N/M + pain + withdraw
- 行为层：mode_idx、max_tokens、reply_length、llm_called
- 记忆层：conversation_history 长度、events 数量、事件原文
- 关系层：每个 user_id 的 warmth、visit_count、tone_avg
- 哈希链：总记录数

所有数据写入 behavior_log.jsonl，每轮一条。不做判断，只记录。
"""

import json
import os
import time

BEHAVIOR_LOG_FILE = "self_check/behavior_log.jsonl"

# 档位名称（仅用于人类可读，不参与判断）
_MODE_NAMES = ["silent", "brief", "short", "normal", "engaged"]


def record_tick(memory, user_id, user_input, reply, behavior, llm_called=True):
    """
    记录一轮交互的完整行为数据。

    参数：
        memory：活记忆字典
        user_id：当前用户 ID
        user_input：用户输入原文
        reply：洛神回复原文
        behavior：behavior 字典（来自 compute_behavior_output）
        llm_called：是否调用了 LLM

    返回：记录的 dict（方便调用者使用）
    """
    # ── 状态层 ──
    climate = memory.get("internal_climate", {})
    self_model = memory.get("self_model", {})

    # ── 行为层 ──
    mode_idx = behavior.get("mode_idx", -1)
    mode_name = _MODE_NAMES[mode_idx] if 0 <= mode_idx < len(_MODE_NAMES) else "unknown"
    max_tokens = behavior.get("max_tokens", 0)

    # ── 记忆层 ──
    relations = memory.get("relations", {})
    user_rel = relations.get(user_id, {})
    conv_history = user_rel.get("conversation_history", [])
    events = user_rel.get("events", [])

    # ── 哈希链行数 ──
    hash_chain_lines = _count_file_lines("hash_chain_v2.log")

    # ── 构建记录 ──
    tick = {
        "tick": memory.get("user_model", {}).get("total_interactions", 0),
        "timestamp": time.time(),
        "user_id": user_id,
        "user_input": user_input[:500],
        "luoshen_reply": reply[:500] if reply else "",
        "state": {
            "energy": climate.get("energy", 0.0),
            "tension": climate.get("tension", 0.0),
            "emotion_intensity": climate.get("emotion_intensity", 0.0),
            "memory_pressure": climate.get("memory_pressure", 0.0),
            "internal_pain": self_model.get("internal_pain", 0.0),
            "withdraw_tendency": self_model.get("withdraw_tendency", 0.0),
        },
        "behavior": {
            "mode_idx": mode_idx,
            "mode_name": mode_name,
            "max_tokens": max_tokens,
            "llm_called": llm_called,
            "reply_length": len(reply) if reply else 0,
            "response_tendency": behavior.get("response_tendency", 0.0),
            "tone_mode_idx": behavior.get("tone_mode_idx", 1),
        },
        "relation": {
            "warmth": user_rel.get("relationship_warmth", 0.0),
            "visit_count": user_rel.get("visit_count", 0),
            "tone_sum": user_rel.get("tone_sum", 0.0),
            "conversation_history_len": len(conv_history),
            "events_count": len(events),
            "recent_events": [e[:100] if isinstance(e, str) else e.get("fact_text", "")[:100] for e in events[-3:]],
        },
        "hash_chain": {
            "records_total": hash_chain_lines,
        },
        "all_relations": {
            uid: {
                "warmth": r.get("relationship_warmth", 0.0),
                "visits": r.get("visit_count", 0),
                "tone_avg": r.get("tone_sum", 0.0) / max(1, r.get("visit_count", 1)),
            }
            for uid, r in relations.items()
        },
    }

    _append_jsonl(BEHAVIOR_LOG_FILE, tick)
    return tick


def read_behavior_log(window=None):
    """
    读取行为日志。

    参数：
        window：最近多少条（None = 全部）

    返回：list of dict
    """
    return _read_jsonl(BEHAVIOR_LOG_FILE, window)


def clear_behavior_log():
    """清空行为日志。"""
    try:
        open(BEHAVIOR_LOG_FILE, "w").close()
    except Exception:
        pass


def _count_file_lines(path):
    """计算文件行数（失败返回 -1）。"""
    try:
        if not os.path.exists(path):
            return 0
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for _ in f:
                count += 1
        return count
    except Exception:
        return -1


def _append_jsonl(path, record):
    """追加一条 JSON 行。"""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _read_jsonl(path, window=None):
    """读取 JSONL 文件。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if window:
            lines = lines[-window:]
        return [json.loads(line) for line in lines if line.strip()]
    except Exception:
        return []
