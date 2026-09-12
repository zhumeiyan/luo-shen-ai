#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_check.behavior_analysis — 整体行为统计分析

对 behavior_log.jsonl 做汇总统计。
所有输出都是连续数值，不用 if-then 判定。

产出：
- 状态均值、标准差、变动范围
- 行为档位分布（每档各出现多少次）
- 回复长度分布
- 关系差异（不同用户的 warmth 标准差）
- 事件频率
"""

import math


def summarize(records):
    """
    对行为记录做汇总统计。

    参数：
        records：behavior_log.read_behavior_log() 的输出

    返回：dict，全部是连续数值和计数
    """
    if not records:
        return {"empty": True, "count": 0}

    n = len(records)

    # ── 状态变量统计 ──
    state_vars = ["energy", "tension", "emotion_intensity", "memory_pressure",
                  "internal_pain", "withdraw_tendency"]
    state_stats = {}
    for var in state_vars:
        values = [r["state"].get(var, 0.0) for r in records if "state" in r]
        if not values:
            continue
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / max(1, len(values))
        std = math.sqrt(variance)
        state_stats[var] = {
            "mean": round(mean, 4),
            "std": round(std, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "range": round(max(values) - min(values), 4),
            "final": round(values[-1], 4),
            "first": round(values[0], 4),
            "net_change": round(values[-1] - values[0], 4),
        }

    # ── 行为档位分布 ──
    mode_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for r in records:
        idx = r.get("behavior", {}).get("mode_idx", -1)
        if idx in mode_counts:
            mode_counts[idx] += 1

    # ── 回复长度统计 ──
    reply_lengths = [r.get("behavior", {}).get("reply_length", 0) for r in records]
    reply_len_mean = sum(reply_lengths) / max(1, n)
    reply_len_std = math.sqrt(
        sum((l - reply_len_mean) ** 2 for l in reply_lengths) / max(1, n)
    )

    # ── LLM 调用率 ──
    llm_called_count = sum(1 for r in records if r.get("behavior", {}).get("llm_called"))

    # ── 关系差异 ──
    # 每个用户的平均 warmth
    user_warmths = {}
    for r in records:
        uid = r.get("user_id", "unknown")
        w = r.get("relation", {}).get("warmth", 0.0)
        if uid not in user_warmths:
            user_warmths[uid] = []
        user_warmths[uid].append(w)

    # 取每个用户的最新 warmth
    user_latest_warmth = {
        uid: vals[-1] for uid, vals in user_warmths.items()
    }
    warmth_values = list(user_latest_warmth.values())
    warmth_spread = max(warmth_values) - min(warmth_values) if len(warmth_values) >= 2 else 0.0

    # ── 哈希链增长 ──
    first_chain = records[0].get("hash_chain", {}).get("records_total", 0)
    last_chain = records[-1].get("hash_chain", {}).get("records_total", 0)
    chain_growth = last_chain - first_chain

    # ── 时间跨度 ──
    first_ts = records[0].get("timestamp", 0)
    last_ts = records[-1].get("timestamp", 0)

    return {
        "empty": False,
        "count": n,
        "time_span_seconds": round(last_ts - first_ts, 1),
        "state": state_stats,
        "behavior": {
            "mode_distribution": mode_counts,
            "reply_length_mean": round(reply_len_mean, 1),
            "reply_length_std": round(reply_len_std, 1),
            "reply_length_min": min(reply_lengths) if reply_lengths else 0,
            "reply_length_max": max(reply_lengths) if reply_lengths else 0,
            "llm_called_count": llm_called_count,
            "llm_called_rate": round(llm_called_count / max(1, n), 3),
        },
        "relations": {
            "per_user_latest_warmth": {uid: round(v, 4) for uid, v in user_latest_warmth.items()},
            "warmth_spreadAcross_users": round(warmth_spread, 4),
            "unique_user_count": len(user_latest_warmth),
        },
        "hash_chain": {
            "first_record_count": first_chain,
            "last_record_count": last_chain,
            "delta": chain_growth,
        },
    }
