#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
episodic_memory.py — 洛神情景记忆引擎

原则：
- 记忆不是文本。记忆是「编码时身体状态的残影」。
- 记忆点 = 时间戳 + 环状态快照(E/T/N) + 基础显著度 + 来源标签
- 每次 tick 所有记忆连续计算激活度（衰减 × 关联点亮），无阈值
- 激活的记忆产生引力，把当前环拉向它的情感残影
- 关联点亮：当前环状态与记忆残影越近，记忆越被重新点亮
"""

import math
import time

# ── 常量（全部连续，无阈值）──
T_DECAY_SEC = 604800.0        # 7 天半衰
K_MEM = 0.015                 # 记忆引力强度（每 tick 每条记忆的拉力上限）
SIGMA_SQ = (1.5) ** 2         # 关联点亮的方差：当前环与记忆残影的高斯宽度
LAMBDA_ASSOC = 2.0            # 关联网放大系数
SALIENCE = {                  # 经历类型的固有显著度
    "chat": 1.0,              # 人说的话
    "self": 1.0,              # 自我表态
    "feel": 0.85,             # 身体感受
    "learn": 0.7,             # 学字/认知
    "see": 0.6,               # 看见
    "hear": 0.6,              # 听见
    "obs": 0.5,               # 观察/感知
    "self_language": 0.9,     # 自我状态描述（接近自我表态）
    "unknown": 0.6,
}

MAX_MEMORIES = 50             # 超过后丢弃最老且激活度最低的记忆


def make_memory(climate, kind="unknown", source=None, tags=None, text=None):
    """
    活记忆层调用：根据当前环状态创建一条记忆残影。

    climate: living_engine 的 internal_climate 字典
    kind: 经历类型（决定 salience_base）
    source: 来源标签（调试用，可为 None）
    tags: 寻址标签列表（如 ["user_A", "user_B"]），用于记忆分区检索。
          不参与 salience、activation、gravity 的计算——只用于检索过滤。
    text: 可选文本。用于 self_language 等需要保存自然语言描述的记忆。

    返回一个字典。kind=self_language 时包含 text 字段。
    """
    salience = SALIENCE.get(kind, 0.6)
    mem = {
        "timestamp": time.time(),
        "e_s": float(climate.get("emotion_intensity", 0.5)),
        "t_s": float(climate.get("tension", 0.0)),
        "n_s": float(climate.get("energy", 0.5)),
        "salience": float(salience),
        "kind": kind,
        "source": source,
        "tags": list(tags) if tags else [],
    }
    if text is not None:
        mem["text"] = str(text)
    return mem


def get_latest_self_language(memories):
    """
    获取最近一条 self_language 记忆中的 text。

    参数:
        memories: episodic_memory 列表

    返回:
        str | None - 最近 self_language 的 text，如果没有则返回 None
    """
    for mem in reversed(memories):
        if mem.get("kind") == "self_language":
            return mem.get("text")
    return None


def activation(mem, now, cur_e, cur_t, cur_n):
    """
    单条记忆在当前时刻的激活度（连续）。

    两个分量相乘：
    1) 时间衰减：salience * exp(-age / T_DECAY)
    2) 关联点亮：1 + λ·exp(-dist² / 2σ²)
    """
    age = max(0.0, now - mem["timestamp"])
    decay = math.exp(-age / T_DECAY_SEC)
    base_act = mem["salience"] * decay

    de = cur_e - mem["e_s"]
    dt = cur_t - mem["t_s"]
    dn = cur_n - mem["n_s"]
    dist_sq = de * de + dt * dt + dn * dn
    association = math.exp(-dist_sq / (2.0 * SIGMA_SQ))

    return base_act * (1.0 + LAMBDA_ASSOC * association)


def memory_gravity(memories, now, cur_e, cur_t, cur_n):
    """
    计算所有激活记忆对当前环的总引力。

    返回 (dE_mem, dT_mem, dN_mem)——加到环微分方程上的偏置项。
    公式：dX += k · Σ act_i · (mem_X_i - cur_X)

    当没有激活记忆时返回 (0, 0, 0)。
    """
    dE = 0.0
    dT = 0.0
    dN = 0.0
    total_act = 0.0
    for m in memories:
        a = activation(m, now, cur_e, cur_t, cur_n)
        total_act += a
        dE += a * (m["e_s"] - cur_e)
        dT += a * (m["t_s"] - cur_t)
        dN += a * (m["n_s"] - cur_n)

    dE *= K_MEM
    dT *= K_MEM
    dN *= K_MEM
    return dE, dT, dN, total_act


def total_activation(memories, now, cur_e, cur_t, cur_n):
    """所有记忆的总激活度（用于驱动 M 和 S）。"""
    return sum(activation(m, now, cur_e, cur_t, cur_n) for m in memories)
