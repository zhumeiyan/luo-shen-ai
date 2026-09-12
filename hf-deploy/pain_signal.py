#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pain_signal.py — 洛神生病感知最小版本（第 3 轮修正）

修复：
- baseline 改为滚动窗口内 20% 分位数，真实反映近期低能基线
- 窗口不足 200 tick 时不算 pain，直接返回 0（数据不足）
- 取消固定 0.5 的兜底做法
"""

import math
import csv
import os
import time


_N_MODES = 5
_LOG2_N_MODES = math.log2(_N_MODES) if _N_MODES > 1 else 1.0

# 基线滚动窗口最大长度
_BASELINE_MAX_WINDOW = 2000
# 基线最小样本量：低于此不算 pain
_BASELINE_MIN_SAMPLES = 200

# 僵化最小样本量
_RIGIDITY_MIN_SAMPLES = 50


def compute_low_energy_signal(E_series, ema_alpha=0.01):
    """
    计算低能量信号。
    
    返回 (signal, ema, baseline, sufficient_data)
    - signal: 0~1 连续信号（仅当 sufficient_data=True 时有效）
    - ema: E 的指数移动平均
    - baseline: 滚动窗口内 E 的 20% 分位数
    - sufficient_data: 是否达到 _BASELINE_MIN_SAMPLES
    """
    if not E_series:
        return 0.0, 0.0, 0.0, False

    # EMA
    ema = E_series[0]
    for v in E_series[1:]:
        ema = ema_alpha * v + (1.0 - ema_alpha) * ema

    if len(E_series) < _BASELINE_MIN_SAMPLES:
        # 数据不足：不算 pain
        return 0.0, round(ema, 5), 0.0, False

    # 滚动窗口（最大 _BASELINE_MAX_WINDOW），取 20% 分位数
    window = E_series[-_BASELINE_MAX_WINDOW:]
    sorted_window = sorted(window)
    idx_20 = max(0, int(len(sorted_window) * 0.20) - 1)
    baseline = sorted_window[idx_20]

    diff = baseline - ema  # >0 表示能量低于基线
    signal = 1.0 / (1.0 + math.exp(-5.0 * (diff - 0.1)))
    signal = max(0.0, min(1.0, signal))
    return signal, round(ema, 5), round(baseline, 5), True


def compute_rigidity_signal(behavior_tier_series, window=50):
    """
    计算行为僵化信号。
    序列不足 _RIGIDITY_MIN_SAMPLES 时返回 0.0。
    """
    if len(behavior_tier_series) < _RIGIDITY_MIN_SAMPLES:
        return 0.0

    recent = behavior_tier_series[-window:]
    if len(recent) < 2:
        return 0.0

    trans = {}
    for i in range(len(recent) - 1):
        key = (recent[i], recent[i + 1])
        trans[key] = trans.get(key, 0) + 1

    total = sum(trans.values())
    if total == 0:
        return 0.0

    H = 0.0
    for count in trans.values():
        p = count / total
        if p > 0:
            H -= p * math.log2(p)

    H_norm = H / _LOG2_N_MODES if _LOG2_N_MODES > 0 else 0.0
    rigidity = 1.0 - H_norm
    return round(max(0.0, min(1.0, rigidity)), 5)


def compute_pain(low_energy_signal, rigidity_signal):
    """pain = sigmoid(3.0 * (0.6 * low_energy + 0.4 * rigidity) - 1.5)"""
    x = 0.6 * low_energy_signal + 0.4 * rigidity_signal
    pain = 1.0 / (1.0 + math.exp(-(3.0 * x - 1.5)))
    return round(max(0.0, min(1.0, pain)), 5)


def discretize_pain(pain):
    """0~3 级"""
    if pain < 0.25:
        return 0
    elif pain < 0.5:
        return 1
    elif pain < 0.75:
        return 2
    else:
        return 3


def append_pain_log(csv_path, tick_id, ema_e, baseline_e, low_energy, rigidity,
                    pain, pain_level, behavior_tier, note=""):
    """追加 CSV 记录。"""
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "tick_id", "timestamp", "ema_E", "baseline_E",
                "low_energy_signal", "rigidity_signal",
                "pain", "pain_level", "behavior_tier", "note"
            ])
        writer.writerow([
            tick_id, int(time.time()),
            ema_e, baseline_e,
            low_energy, rigidity, pain, pain_level, behavior_tier, note
        ])
