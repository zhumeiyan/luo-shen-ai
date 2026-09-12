#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_check.state_log — 状态历史日志

洛神每轮交互后记录一份状态快照到 state_log.jsonl，
供趋势分析使用。

格式（每行一条 JSON）：
{"timestamp": ..., "energy": -0.47, "tension": 0.05, "emotion_intensity": 0.01,
 "memory_pressure": 0.0, "internal_pain": 0.0, "withdraw_tendency": 0.28}

只追加，不修改。
"""

import json
import os
import time

STATE_LOG_FILE = "self_check/state_log.jsonl"


def _now():
    return round(time.time(), 2)


def append_snapshot(memory, user_id="primary"):
    """
    将当前状态快照追加到 state_log.jsonl。

    应在每轮对话结束时调用。
    返回写入的 dict（便于测试）。
    """
    from .snapshot import snapshot_state

    snap = snapshot_state(memory)
    snap["user_id"] = user_id

    log_path = STATE_LOG_FILE

    # 确保目录存在
    dir_path = os.path.dirname(log_path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

    # 追加写
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")

    return snap


def read_history(window=None):
    """
    读取状态历史。

    输入：
        window：int 或 None。若为 int，返回最近 window 条；若为 None，返回全部。

    输出：
        [dict, ...]  按时间从旧到新排列。
    """
    log_path = STATE_LOG_FILE

    if not os.path.exists(log_path):
        return []

    records = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if window and len(records) > window:
        records = records[-window:]

    return records


def clear_history():
    """
    清空状态日志（仅在测试或重置时使用）。
    """
    log_path = STATE_LOG_FILE
    if os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("")
