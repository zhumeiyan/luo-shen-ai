#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_check.trend — 趋势计算

对状态变量计算：
- 方向（线性回归斜率）—— 正=上升，负=下降，零=平稳
- 幅度（变动了多少）
- 偏离度（相对历史基线的标准差倍数）

所有输出都是连续数值，不用硬标签。
"""


def _linear_slope(values):
    """
    计算一组数值的线性回归斜率（最小二乘法）。

    输入：[y0, y1, y2, ..., yn]
    输出：float，斜率值（正=上升，负=下降，零=平稳）

    不判断"是上升还是下降"——由调用者根据正负号和幅度自行判断。
    """
    n = len(values)
    if n < 2:
        return 0.0

    # x = [0, 1, 2, ..., n-1]
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if abs(denominator) < 1e-10:
        return 0.0

    return numerator / denominator


def _deviation_from_baseline(values, current):
    """
    计算当前值相对于历史基线的偏离度（标准差倍数）。

    输入：
        values：历史值列表（不含当前值）
        current：当前值

    输出：float，偏离度（0=在基线上，1=1个标准差，-1=1个标准差下）

    不判断"正常/异常"——由调用者自行判断。
    """
    n = len(values)
    if n < 2:
        return 0.0

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance ** 0.5

    if std < 1e-10:
        # 历史值几乎无变化，任何偏离都很显著
        return 0.0 if abs(current - mean) < 1e-10 else 3.0

    return (current - mean) / std


def _magnitude(values):
    """
    计算变动幅度（最大值 - 最小值）。

    输出：float，非负，表示这段序列的总变动范围。
    """
    if len(values) < 2:
        return 0.0
    return max(values) - min(values)


def trend_analysis(history_list, window=20):
    """
    对状态历史做趋势分析。

    输入：
        history_list：[{"energy": x, "tension": y, ...}, ...]
                     按时间从旧到新排列
        window：分析窗口大小（最近多少轮）

    输出：
        {
            "energy": {
                "slope": -0.05,       # 斜率（正=上升，负=下降，零=平稳）
                "magnitude": 0.8,     # 变动幅度
                "deviation": 1.2,     # 偏离度（标准差倍数）
                "current": -0.47,     # 当前值
                "baseline_mean": 0.3  # 历史基线均值
            },
            "tension": {...},
            ...
            "window_size": 20,
            "sequence_length": 25
        }

    无硬阈值判断。所有输出都是连续数值。
    """
    if not history_list:
        return {"window_size": window, "sequence_length": 0}

    variables = ["energy", "tension", "emotion_intensity", "memory_pressure",
                 "internal_pain", "withdraw_tendency"]

    # 取最近 window 轮
    recent = history_list[-window:]
    full = history_list  # 全部历史用于基线

    result = {"window_size": window, "sequence_length": len(history_list)}

    for var in variables:
        values_full = [h.get(var, 0.0) for h in full]
        values_recent = [h.get(var, 0.0) for h in recent]

        current = values_full[-1] if values_full else 0.0
        slope = _linear_slope(values_recent)
        magnitude = _magnitude(values_recent)

        # 偏离度以 window 前的历史为基线（避免 window 内的数据自我参考）
        pre_window = history_list[:-window] if len(history_list) > window else []
        if len(pre_window) >= 2:
            pre_values = [h.get(var, 0.0) for h in pre_window]
            deviation = _deviation_from_baseline(pre_values, current)
        else:
            # 数据不足，用全量历史
            deviation = _deviation_from_baseline(values_full[:-1], current)

        baseline_mean = sum(values_full[:-1]) / max(1, len(values_full) - 1)

        result[var] = {
            "slope": round(slope, 6),
            "magnitude": round(magnitude, 4),
            "deviation": round(deviation, 4),
            "current": round(current, 4),
            "baseline_mean": round(baseline_mean, 4),
        }

    return result
