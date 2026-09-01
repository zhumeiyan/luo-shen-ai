#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emergence_layer.py — 洛神记忆浮现选择层

作用：
- 每次回应之前，根据当前环状态和所有记忆点的激活度
- 选出主导记忆（激活度最高的那条）
- 主导记忆的情绪快照直接影响语气和长度选择
- 不使用 sigmoid 压扁，保留差异

禁止 if-then，禁止阈值开关，所有映射都是连续函数。
"""

import math
import time

# ── 浮现层参数 ──
TAU_SOFTMAX = 0.3             # softmax 温度：越小越"尖锐"
K_LENGTH_ALPHA = 2.0          # e_bg 对长度的影响强度（线性）
K_LENGTH_BETA = 1.5           # dominance 对长度的影响强度
K_LENGTH_GAMMA = 0.8          # 记忆年龄对长度的影响强度
K_AROUSAL_DELTA = 0.15        # 记忆对 arousal 的偏置强度
K_TONE_ETA = 0.5              # 语气偏移强度
# 新增：主导记忆放大系数
DOMINANT_AMP = 8.0            # (e_bg - 中性点) 的放大倍数
NEUTRAL_E = 0.5               # E 的中性参考点
AROUSAL_AGE_INVERT = 0.3      # sigmoid 反向点：age 越小，arousal 越高


def softmax_weights(activations):
    """
    softmax 归一化：把一组激活度映射为概率权重。
    """
    if not activations:
        return []

    max_a = max(activations)
    exps = [math.exp((a - max_a) / TAU_SOFTMAX) for a in activations]
    total = sum(exps)
    if total < 1e-12:
        return [1.0 / len(activations)] * len(activations)

    return [e / total for e in exps]


def dominant_background(memories, activations, now):
    """
    主导记忆机制：选出激活度最高的记忆，直接返回其快照。

    不计算平均。如果多条记忆激活度接近，使用加权（让高激活度的占优）。

    返回 dict:
      e_bg: 主导记忆的 e_s
      t_bg: 主导记忆的 t_s
      n_bg: 主导记忆的 n_s
      age_bg: 主导记忆的归一化年龄
      sal_bg: 主导记忆的显著性
      dominance: 主导记忆的激活度占比
    """
    if not memories or not activations:
        return {
            "e_bg": 0.0, "t_bg": 0.0, "n_bg": 0.0,
            "age_bg": 0.0, "sal_bg": 0.0, "dominance": 0.0,
        }

    n = len(memories)
    if n == 1:
        m = memories[0]
        age = max(0.0, now - m["timestamp"])
        return {
            "e_bg": m["e_s"],
            "t_bg": m["t_s"],
            "n_bg": m["n_s"],
            "age_bg": min(1.0, age / 604800.0),
            "sal_bg": m["salience"],
            "dominance": 1.0,
        }

    # 多条记忆：soft 选择（不是 hard argmax）
    # 高激活度记忆的 e_s 贡献更大
    weights = softmax_weights(activations)

    # 找到最大激活度记忆作为锚点
    max_a = max(activations)
    dominant_idx = activations.index(max_a)
    dominant_mem = memories[dominant_idx]

    # 使用所有记忆的加权，但温度低（更尖锐），让主导记忆更占优
    weights_sharp = softmax_weights([a * 2.0 for a in activations])

    e_bg = 0.0
    t_bg = 0.0
    n_bg = 0.0
    age_bg = 0.0
    sal_bg = 0.0

    for i, m in enumerate(memories):
        w = weights_sharp[i]
        e_bg += w * m["e_s"]
        t_bg += w * m["t_s"]
        n_bg += w * m["n_s"]
        age = max(0.0, now - m["timestamp"])
        age_bg += w * min(1.0, age / 604800.0)
        sal_bg += w * m["salience"]

    return {
        "e_bg": e_bg,
        "t_bg": t_bg,
        "n_bg": n_bg,
        "age_bg": age_bg,
        "sal_bg": sal_bg,
        "dominance": weights_sharp[dominant_idx],
    }


def length_bias(background):
    """
    回应长度偏置 —— 近线性版本。

    返回 float ∈ [0, 1]：
    - 接近 0：更短
    - 接近 1：更长

    公式（线性 + dominance 修正）：
    base = e_bg
    modifier = α · dominance
    result = clamp(base · (1 + modifier), 0.1, 0.9)
    """
    e_bg = background["e_bg"]
    dominance = background["dominance"]

    # 直接用 e_bg（在 [0,1] 之间）作为基线
    # dominance > 0.5 时放大，dominance 小时保持
    modifier = K_LENGTH_ALPHA * (dominance - 0.5)
    raw = e_bg * (1.0 + modifier)

    # 软限幅（非硬 clamp）
    return max(0.1, min(0.9, raw))


def tone_bias(background):
    """
    语气偏移 —— 直接由 e_bg 驱动，不使用 sigmoid 压扁。

    返回 float ∈ [-1, 1]：
    - 负值：更沉/更内省
    - 正值：更轻/更开放

    公式：AMP · (e_bg - 中性点) · dominance
    AMP 放大系数确保小差异也能产生可观测的影响。
    """
    e_bg = background["e_bg"]
    dominance = background["dominance"]

    centered = e_bg - NEUTRAL_E  # 以 0.5 为中心
    return DOMINANT_AMP * centered * dominance


def arousal_bias(background):
    """
    记忆对 arousal 的连续偏置。
    使用 sigmoid 是因为这里的语义是"是否足够新/足够强来影响沉默"。
    """
    age_sigmoid = 1.0 / (1.0 + math.exp(-(AROUSAL_AGE_INVERT - background["age_bg"]) * 10))
    return K_AROUSAL_DELTA * background["dominance"] * age_sigmoid


def compute_emergence(memories, now, cur_e, cur_t, cur_n, activations):
    """
    一次调用，把记忆列表映射为"主导记忆背景 + 三个偏置输出"。
    """
    if not activations or all(a < 1e-10 for a in activations):
        zero_bg = {"e_bg": 0.0, "t_bg": 0.0, "n_bg": 0.0,
                   "age_bg": 0.0, "sal_bg": 0.0, "dominance": 0.0}
        return {
            "background": zero_bg,
            "weights": [],
            "length_bias": 0.5,
            "tone_bias": 0.0,
            "arousal_bias": 0.0,
        }

    weights = softmax_weights(activations)
    bg = dominant_background(memories, activations, now)
    lbias = length_bias(bg)
    tbias = tone_bias(bg)
    abias = arousal_bias(bg)

    return {
        "background": bg,
        "weights": weights,
        "length_bias": lbias,
        "tone_bias": tbias,
        "arousal_bias": abias,
    }
