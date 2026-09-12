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

# ─── 慢压力感知参数 ───
# 让浮现层能"感知"ring_state中的relational_pressure_ema
# pressure_ema ∈ 约 [-0.6, +0.6]（500 tick积累）
K_PRESSURE_TONE = 0.25       # 压力对语气的调制强度（负压力 → 语气下沉）
K_PRESSURE_AROUSAL = 0.15    # 压力对唤醒的调制强度（负压力 → 唤醒降低 → 更谨慎）
K_PRESSURE_MEMORY = 0.07     # 压力对记忆激活度的连续调制（±5~6%，不压过记忆本身）

# ─── 浮现叙事层参数 ───
# 叙事势：由四个连续分量相乘构成，代表“来自历史的话头强度”
NARRATIVE_DECAY_TAU = 3600.0       # 未闭合情感衰减：1 小时半衰
NARRATIVE_EPSILON = 0.05           # 门限：低于此值不注入 LLM
NARRATIVE_MAX_AGE = 604800.0       # 7 天加权最大记忆年龄
NARRATIVE_SIGMA = 0.12             # 高斯混合带宽（E/T/N 空间距离）
NARRATIVE_OPEN_SALIENCE_THRESH = 0.7  # 闭合判定阈值（连续软化）


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


# ─── 浮现叙事层 ───
# 四个分量连续计算，全部 [0, 1]


def _affective_cluster_density(memories):
    """
    分量 A：情感聚集密度。
    对 E/T/N 空间做软高斯混合，找最密的聚集区。
    """
    if len(memories) < 2:
        # 1 条记忆：聚集度连续地低（1/N 归一化）
        return 1.0 / max(1.0, len(memories))

    # 以记忆点自身为聚类中心候选
    best_density = 0.0
    two_sigma_sq = 2.0 * (NARRATIVE_SIGMA ** 2)
    for j, mj in enumerate(memories):
        density_j = 0.0
        ej, tj, nj = mj["e_s"], mj["t_s"], mj["n_s"]
        for i, mi in enumerate(memories):
            de = mi["e_s"] - ej
            dt = mi["t_s"] - tj
            dn = mi["n_s"] - nj
            dist_sq = de * de + dt * dt + dn * dn
            density_j += math.exp(-dist_sq / two_sigma_sq)
        if density_j > best_density:
            best_density = density_j

    # 归一化到 [0, 1]：除以聚集点数（完全聚集时 = 1）
    return best_density / len(memories)


def _temporal_focus(memories, now):
    """
    分量 B：时间焦点。
    记忆的归一化时间聚集度（标准差越小 → 越聚集 → 值越高）。
    """
    if len(memories) < 2:
        return 0.5  # 1 条：中性的聚集度

    ages = [max(0.0, now - m["timestamp"]) for m in memories]
    mean_age = sum(ages) / len(ages)
    var_age = sum((a - mean_age) ** 2 for a in ages) / len(ages)
    std_age = math.sqrt(var_age)
    # 归一化：std_age / max_age ∈ [0, 1] → 聚焦度 = 1 - 归一化
    norm_std = min(1.0, std_age / NARRATIVE_MAX_AGE)
    return 1.0 - norm_std


def _open_arousal_residual(memories, now):
    """
    分量 C：未闭合情感残留。
    高 salience 但从未被洛神回应的记忆，按时间衰减求和。
    使用连续软化（sigmoid）代替硬阈值。
    """
    residual = 0.0
    for m in memories:
        # 软化判定：salience 在阈值附近的连续权重
        salience_factor = 1.0 / (1.0 + math.exp(
            -(m["salience"] - NARRATIVE_OPEN_SALIENCE_THRESH) * 10
        ))
        age = max(0.0, now - m["timestamp"])
        decay = math.exp(-age / NARRATIVE_DECAY_TAU)
        residual += salience_factor * decay

    # 压缩到 [0, 1] 用 tanh
    return math.tanh(residual / 1.5)


def _present_past_contrast(memories, cur_e, cur_t, cur_n):
    """
    分量 D：今昔反差。
    当前环状态与记忆重心的欧氏距离 → [0, 1]。n
    """
    if not memories:
        return 0.0
    # 记忆重心
    mean_e = sum(m["e_s"] for m in memories) / len(memories)
    mean_t = sum(m["t_s"] for m in memories) / len(memories)
    mean_n = sum(m["n_s"] for m in memories) / len(memories)

    d_e = cur_e - mean_e
    d_t = cur_t - mean_t
    d_n = cur_n - mean_n
    # 归一化距离：除以 √(3)（最大可能距离）
    raw_dist = min(1.0, math.sqrt(d_e**2 + d_t**2 + d_n**2) / math.sqrt(3.0))
    return raw_dist


def compute_narrative_potential(memories, cur_e, cur_t, cur_n, now,
                                pain_at_encoding_avg=None):
    """
    计算叙事势：当前记忆中"来自历史的话头强度"。

    pain_at_encoding_avg: 当前所用记忆的平均 pain_at_encoding 值（连续）。
      若提供，则叠加 pain_at_encoding_avg * 0.15 到 potential 上（clamp 回 [0,1]）。

    返回 dict:
      potential: float [0, 1]
      frame_weights: dict 四个连续框架权重
      structure_hints: dict 抽象结构提示
    """
    if not memories or len(memories) < 2:
        return {
            "potential": 0.0,
            "frame_weights": {
                "pattern": 0.0,
                "unspoken": 0.0,
                "contrast": 0.0,
                "present": 1.0,
            },
            "structure_hints": {
                "repetition_count": len(memories),
                "temporal_span": "无积累",
                "closure_state": "absent",
            },
        }

    A = _affective_cluster_density(memories)
    B = _temporal_focus(memories, now)
    C = _open_arousal_residual(memories, now)
    D = _present_past_contrast(memories, cur_e, cur_t, cur_n)

    potential = A * B * C * D
    potential = max(0.0, min(1.0, potential))

    # 生病感知：pain_at_encoding 通过记忆间接调制叙事势（不直接进行为公式）
    if pain_at_encoding_avg is not None and pain_at_encoding_avg > 0.0:
        potential = potential + float(pain_at_encoding_avg) * 0.15
        potential = max(0.0, min(1.0, potential))

    w_pattern = A * C
    w_unspoken = C * D
    w_contrast = D * (1.0 - B)
    w_present = (1.0 - A) * (1.0 - C)

    w_sum = max(1e-10, w_pattern + w_unspoken + w_contrast + w_present)
    frame_weights = {
        "pattern": w_pattern / w_sum,
        "unspoken": w_unspoken / w_sum,
        "contrast": w_contrast / w_sum,
        "present": w_present / w_sum,
    }

    closure_state = "resolved" if C < 0.2 else ("lingering" if C < 0.5 else "unresolved")

    structure_hints = {
        "repetition_count": len(memories),
        "temporal_span": "最近 {:d} 轮".format(len(memories)),
        "closure_state": closure_state,
    }

    return {
        "potential": potential,
        "frame_weights": frame_weights,
        "structure_hints": structure_hints,
    }


def compute_emergence(memories, now, cur_e, cur_t, cur_n, activations,
                      pressure_ema=None):
    """
    一次调用，把记忆列表映射为"主导记忆背景 + 三个偏置 + 叙事势"。

    pressure_ema: 可选，ring_state["relational_pressure_ema"]。
                  用户提供时，用它线性调制 tone_bias 和 arousal_bias，
                  让浮现层能感知用户输入历史积累的"关系压力"。
                  无压力数据时（默认 None）退化为纯记忆驱动。
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
            "narrative_potential": 0.0,
            "narrative_frame_weights": {
                "pattern": 0.0, "unspoken": 0.0,
                "contrast": 0.0, "present": 1.0,
            },
            "narrative_hints": {
                "repetition_count": 0,
                "temporal_span": "无积累",
                "closure_state": "absent",
            },
        }

    weights = softmax_weights(activations)
    bg = dominant_background(memories, activations, now)
    lbias = length_bias(bg)
    tbias = tone_bias(bg)
    abias = arousal_bias(bg)

    # ─── 生病感知：从已激活记忆中提取 pain_at_encoding（加权平均） ───
    # 只对带有 pain_at_encoding 字段的记忆进行加权平均（兼容无该字段的旧记忆）
    pain_weighted_sum = 0.0
    pain_weight_total = 0.0
    for i, m in enumerate(memories):
        p = m.get("pain_at_encoding")
        if p is not None:
            pain_weighted_sum += weights[i] * float(p)
            pain_weight_total += weights[i]
    pain_at_encoding_avg = (pain_weighted_sum / pain_weight_total) if pain_weight_total > 1e-10 else None

    # ─── 慢压力感知调制 ───
    # pressure_ema < 0（负向历史）→ 语气下沉 + 唤醒降低（更克制）
    # pressure_ema > 0（正向历史）→ 语气变轻 + 唤醒升高（更开放）
    # 连续线性，无 if-then，系数小确保不压倒记忆自身的信号
    # 压力对记忆激活度的连续调制（不直接修改 activations，由调用方乘上）
    # 正向历史 → 什么记忆都更容易浮起；负向历史 → 记忆更沉
    _pressure_memory_mod = 1.0
    if pressure_ema is not None:
        tbias += K_PRESSURE_TONE * pressure_ema
        abias += K_PRESSURE_AROUSAL * pressure_ema
        _pressure_memory_mod = 1.0 + K_PRESSURE_MEMORY * pressure_ema

    # 计算叙事势（传入 pain_at_encoding_avg，让痛苦记忆间接调制叙事势）
    narrative = compute_narrative_potential(memories, cur_e, cur_t, cur_n, now,
                                            pain_at_encoding_avg=pain_at_encoding_avg)

    return {
        "background": bg,
        "weights": weights,
        "length_bias": lbias,
        "tone_bias": tbias,
        "arousal_bias": abias,
        "pressure_memory_mod": _pressure_memory_mod,
        "narrative_potential": narrative["potential"],
        "narrative_frame_weights": narrative["frame_weights"],
        "narrative_hints": narrative["structure_hints"],
    }
