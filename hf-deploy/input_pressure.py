#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
input_pressure.py —— 用户输入情感压力提取与环偏置

通道功能：
  user_input → LLM 情感判断 (valence ∈ [-1, 1], arousal ∈ [0, 1])
  → 计算 val_pressure 和 aro_pressure
  → 在交互后注入 active_context
  → environment_tick 读取并施加压力到微分方程
"""

import json
import time
import math

# ── 压力系数（适度放大，使 A/B 记忆差异达到 0.05-0.1 量级）──
KAPPA_E = 0.06       # E 通道：val_pressure 驱动情绪方向（从 0.03 提到 0.06）
KAPPA_T = 0.04       # T 通道：val_pressure 影响张力（从 0.02 提到 0.04）
KAPPA_N = 0.04       # N 通道：aro_pressure 驱动能量变化
N_BASELINE = 0.5     # N 的基线参考

# 衰减
PRESSURE_DECAY_TICKS = 120   # 120 tick（约 40 秒 @ dt=0.3s）衰减到 0.37


def _call_llm_sentiment(user_input):
    """
    调用 LLM 对用户输入做情感判断。
    返回 (valence, arousal) 两个连续浮点数。

    valence ∈ [-1, 1]：-1 = 极度负面, 0 = 中性, +1 = 极度正面
    arousal ∈ [0, 1]：0 = 平静, 1 = 高度激动

    使用 system_prompt_override 将情感分析 prompt 注入系统角色，
    JSON 格式保证输出可结构化解析。

    如果调用失败或解析失败，fallback (0.0, 0.5)，等价于无压力。
    """
    try:
        from llm_interface import call_llm
        # 构造情感分析 directive：system_prompt_override 替换系统 prompt
        sentiment_directive = {
            "system_prompt_override": (
                "你是一个情感分析器。根据用户输入，输出两个连续数值：\n"
                "  valence: -1.0 (极度负面) 到 +1.0 (极度正面)，0.0 = 中性\n"
                "  arousal: 0.0 (平静/麻木) 到 1.0 (高度激动/紧张/恐惧)\n"
                "只返回 JSON，不返回其他内容。\n"
                "格式：{\"valence\": <float>, \"arousal\": <float>}\n"
                "示例：{\"valence\": -0.6, \"arousal\": 0.7}"
            ),
            "intent": f"用户输入：「{user_input}」",
            "emotion_tone": "平静",
            "strategy_name": "sentiment_analysis",
            "constraints": {"max_length": 50},
            "context_for_llm": {},
        }
        # 需要一个最简 memory 对象
        memory_stub = {
            "self_model": {"emotion": {"primary": "平静"}},
            "user_model": {"intimacy": {"value": 0.5}},
        }
        raw = call_llm(sentiment_directive, memory_stub)
        if raw:
            # 从 LLM 输出中解析 JSON
            text = raw.strip()
            # 可能包裹在 ```json ``` 中
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            parsed = json.loads(text)
            valence = float(parsed.get("valence", 0.0))
            arousal = float(parsed.get("arousal", 0.5))
            # 钳制到合法区间
            valence = max(-1.0, min(1.0, valence))
            arousal = max(0.0, min(1.0, arousal))
            return valence, arousal
    except Exception:
        pass

    # fallback：中性无压力 — 连续到零注入
    return 0.0, 0.5


def extract_input_pressure(memory, user_input):
    """
    从 user_input 提取情感压力，写入 memory["active_context"]["input_pressure"]。

    返回 (valence, arousal) 元组。

    压力数据格式（写入 memory）：
    {
        "valence": float,
        "arousal": float,
        "applied_at": float (tick_id),
    }
    """
    valence, arousal = _call_llm_sentiment(user_input)

    # 写入 active_context
    if "active_context" not in memory:
        memory["active_context"] = {}

    memory["active_context"]["input_pressure"] = {
        "valence": round(valence, 4),
        "arousal": round(arousal, 4),
        "applied_at": time.time(),
    }

    return valence, arousal


def pressure_decay_factor(elapsed_ticks):
    """
    压力随 tick 数指数衰减。
    elapsed_ticks: 压力注入后经过的 tick 数
    返回 [0, 1]
    """
    return math.exp(-elapsed_ticks / PRESSURE_DECAY_TICKS)


def current_pressure(mem_pressure, current_tick_id):
    """
    读取已存储的压力，结合衰减因子返回当前有效压力。

    mem_pressure: memory["active_context"]["input_pressure"] 字典
    current_tick_id: 当前 tick_id

    如果 pressure 中没有 applied_at_tick，则用时间差计算 elapsed。
    返回字典：
    {
        "val_pressure": float,   # valence × arousal 方向性强度
        "aro_pressure": float,  # 纯唤醒 ∈ [0, 1]
        "decay": float,         # 当前衰减因子
    }
    """
    if not mem_pressure:
        return {"val_pressure": 0.0, "aro_pressure": 0.5, "decay": 0.0}

    valence = mem_pressure.get("valence", 0.0)
    arousal = mem_pressure.get("arousal", 0.5)
    applied_at_tick = mem_pressure.get("applied_at_tick", None)

    if applied_at_tick is not None:
        elapsed = max(0, current_tick_id - applied_at_tick)
    else:
        # 用时间差估算 applied_at 对应的 tick
        applied_at_ts = mem_pressure.get("applied_at", 0)
        elapsed_ts = time.time() - applied_at_ts
        elapsed = int(elapsed_ts / 0.33)  # 假设 dt ≈ 0.33s
        elapsed = max(0, elapsed)

    decay = pressure_decay_factor(elapsed)

    val_pressure = valence * arousal  # 有方向性的唤醒 ∈ [-1, 1]
    aro_pressure = arousal              # 纯唤醒 ∈ [0, 1]

    return {
        "val_pressure": val_pressure,
        "aro_pressure": aro_pressure,
        "decay": decay,
    }


def pressure_differentials(mem_pressure, current_tick_id):
    """
    计算当前 tick 的压力微分项（加到 dE/dT/dN 上的量）。

    返回字典：
    {
        "dE_pressure": float,
        "dT_pressure": float,
        "dN_pressure": float,
        "decay": float,
    }
    """
    p = current_pressure(mem_pressure, current_tick_id)
    d = p["decay"]

    if d < 0.001:
        # 衰减已尽，几乎无影响
        return {"dE_pressure": 0.0, "dT_pressure": 0.0, "dN_pressure": 0.0, "decay": d}

    dE = KAPPA_E * p["val_pressure"] * d
    dT = KAPPA_T * p["val_pressure"] * d
    dN = KAPPA_N * (p["aro_pressure"] - N_BASELINE) * d

    return {
        "dE_pressure": dE,
        "dT_pressure": dT,
        "dN_pressure": dN,
        "decay": d,
    }
