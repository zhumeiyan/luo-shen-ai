#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_check.report — 自我报告生成

将趋势分析结果转化为人类（和 LLM）可读的文本。
不做判断，只描述趋势和偏离度。
"""


def _describe_direction(slope):
    """
    用连续的方式描述方向。
    不用"上升/下降/平稳"硬标签，而是说"在往前走/在往回落/基本没动"。
    """
    if slope > 0.01:
        return "在上升"
    elif slope < -0.01:
        return "在下降"
    else:
        return "基本平稳"


def _describe_deviation(deviation):
    """
    用连续的方式描述偏离度。
    不说"正常/异常"，说"在典型的范围内"或"偏离了 N 个标准差"。
    """
    abs_dev = abs(deviation)
    if abs_dev < 0.5:
        return "在典型的范围内"
    elif abs_dev < 1.0:
        return f"偏离均值 {abs_dev:.1f} 个标准差"
    elif abs_dev < 2.0:
        return f"偏离均值 {abs_dev:.1f} 个标准差（偏向{'高' if deviation > 0 else '低'}）"
    else:
        return f"显著偏离均值 {abs_dev:.1f} 个标准差"


def trend_to_text(var_name, trend_data):
    """
    将单个变量的趋势数据转化为一行描述文本。
    """
    if not trend_data:
        return f"- {var_name}：暂无数据"

    slope = trend_data.get("slope", 0.0)
    current = trend_data.get("current", 0.0)
    magnitude = trend_data.get("magnitude", 0.0)
    deviation = trend_data.get("deviation", 0.0)

    direction = _describe_direction(slope)
    dev_text = _describe_deviation(deviation)

    return (
        f"- {var_name}：当前 {current:.2f}，{direction}"
        f"（幅度 {magnitude:.2f}，{dev_text}）"
    )


def self_report(memory, trend_data, user_id=None):
    """
    生成自我报告。

    输入：
        memory：活记忆字典
        trend_data：来自 trend_analysis() 的输出
        user_id：可选，要包含的关系用户ID

    输出：
        {
            "text": "可读文本",
            "raw": trend_data,
            "timestamp": ...,
            "relations": {...} or None
        }
    """
    import time

    if not trend_data or trend_data.get("sequence_length", 0) == 0:
        return {
            "text": "[自查] 暂无状态历史数据。",
            "raw": trend_data,
            "timestamp": time.time(),
            "relations": None,
        }

    lines = ["[自查]"]

    # 只描述主要变量
    main_vars = ["energy", "internal_pain", "withdraw_tendency", "tension"]
    var_labels = {
        "energy": "活力",
        "internal_pain": "疼痛感",
        "withdraw_tendency": "退缩倾向",
        "tension": "张力",
    }

    for var in main_vars:
        if var in trend_data:
            label = var_labels.get(var, var)
            lines.append(trend_to_text(label, trend_data[var]))

    # 窗口信息
    window = trend_data.get("window_size", 0)
    seq_len = trend_data.get("sequence_length", 0)
    lines.append(f"（基于最近 {min(window, seq_len)} 轮 / 共 {seq_len} 轮）")

    # 关系状态（可选）
    relations_block = None
    if user_id:
        from .snapshot import snapshot_relations
        rel = snapshot_relations(memory, user_id)
        if rel["total_turns"] > 0:
            relations_block = (
                f"[关系] 与 {user_id} 的亲密度 {rel['warmth']:.2f}，"
                f"累计 {rel['total_turns']} 轮，平均语气 {rel['tone_avg']:.2f}"
            )
            lines.append(relations_block)

    return {
        "text": "\n".join(lines),
        "raw": trend_data,
        "timestamp": time.time(),
        "relations": relations_block,
    }


def self_report_compact(memory, trend_data, user_id=None):
    """
    生成单行紧凑版自我报告（适合注入 LLM 的 system prompt）。
    """
    if not trend_data or trend_data.get("sequence_length", 0) == 0:
        return "[自查] 暂无数据"

    energy = trend_data.get("energy", {})
    pain = trend_data.get("internal_pain", {})
    withdraw = trend_data.get("withdraw_tendency", {})

    parts = []
    for label, data in [("活力", energy), ("疼痛", pain), ("退缩", withdraw)]:
        if data:
            direction = _describe_direction(data.get("slope", 0))
            parts.append(f"{label}{direction}({data.get('current', 0):.2f})")

    return "[自查] " + " / ".join(parts)
