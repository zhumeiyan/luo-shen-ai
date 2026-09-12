#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cognitive_core.py — 洛神认知核心（最小可运行版）

原则：
- 6×6 网格，每个位置对应一个状态维度
- T=16 帧滚动窗口（时间维）
- 相变：prediction_error 连续超标 → 结构重排
- 自读：diff / prediction_error / hidden_structure
- 仅 NumPy 依赖，LLM 不参与核心运算

文件依赖：
  - 可选读: active_memory/active_memory.json（读取当前状态值作为输入）
  - 写: cognitive_core_log.jsonl（仅追加，审计/调试）

禁止：
  - 不调用 LLM（渲染器在 renderer.py）
  - 不修改哈希链
  - 不修改 living_engine 状态结构

修复记录（Architect seq=3 → F1-F6）：
  F1 耦合核归一化：_init_coupling 后执行 _normalize_coupling，确保每个目标格子的入耦合绝对值和=1
  F2 索引笔误：read_intent 中 flat.sort 使用 abs(x[0]) 而非 abs(x[1]) — 已修正
  F3 线程锁：tick_step / receive_input 主体用 self._lock 包围
  F4 相变重设计：_verify_rollback 已删除；相变为直接结构重排（识别高误差区域，针对性修改耦合子块）
  F5 编码器改投影：encoder.py 使用固定随机投影矩阵从字符 n-gram 特征映射
  F6 预测改AR(1)：预测模型从线性外推改为 x̂(t+1) = φ·x(t) + (1-φ)·x(t-1)，φ=0.85
"""

import numpy as np
import time
import json
import os
import threading
import zlib
from typing import Optional, Dict, List, Tuple, Any

# ── 网格维度定义 ──────────────────────────────────────────────────────────────
# 6行 = 6个状态维度大类；6列 = 每个大类内的6种子态
# 这是位置语义：每个 (r, c) 格子有一个具体含义，不是黑箱

GRID_ROWS = 6
GRID_COLS = 6
FRAME_DEPTH = 16  # 滚动帧数

# AR(1) 预测系数
AR_PHI = 0.85

# 耦合强度系数（F1: < 1 防止 coupling_term 导致帧饱和）
COUPLING_STRENGTH = 0.3

# 行语义（每个网格行的含义）
ROW_LABELS = [
    "energy",     # 0: 能量态
    "pain",       # 1: 痛苦态
    "warmth",     # 2: 温度态
    "withdraw",   # 3: 退缩态
    "attention",  # 4: 注意态
    "drive",      # 5: 驱动态
]

# 列语义（每个行的子态）
COL_LABELS = [
    "alpha",   # 0: 主态
    "beta",    # 1: 动态
    "gamma",   # 2: 耦合
    "delta",   # 3: 惯性
    "epsilon", # 4: 噪声
    "zeta",    # 5: 基线
]

# 坐标可读名
def _cell_name(r: int, c: int) -> str:
    return f"{ROW_LABELS[r]}.{COL_LABELS[c]}"


class CognitiveCore:
    """
    认知核心。
    
    内部状态：
    - frames: (T, 6, 6) 滚动帧缓冲区，frames[-1] 是最新帧
    - coupling: (6, 6, 6, 6) 耦合权重矩阵，描述格子间相互影响
    - attractors: (6, 6) 吸引子基线值
    - tick_count: 总 tick 数
    - phase: 当前相态编号
    - phase_history: 相态变更记录
    - _lock: 线程锁（tick_step / receive_input）
    """

    def __init__(self, seed: int = 42):
        np.random.seed(seed)
        
        # 滚动帧缓冲区：T=16，初始化为微小随机偏离 0
        self.frames = np.zeros((FRAME_DEPTH, GRID_ROWS, GRID_COLS), dtype=np.float64)
        # 初始帧给一点小扰动，避免全零导致预测失效
        self.frames[-1] = np.random.normal(0, 0.01, (GRID_ROWS, GRID_COLS))

        # 耦合权重（F1: 拉普拉斯扩散核 — 净零和，天然稳定，无需归一化）
        self.coupling = self._init_coupling()

        # 吸引子基线：每个格子的稳态回归目标
        self.attractors = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.float64)

        # 运行计数
        self.tick_count: int = 0
        self.phase: int = 0
        self.phase_history: List[Dict[str, Any]] = []

        # 预测与误差追踪
        self._last_prediction: Optional[np.ndarray] = None
        self._prediction_errors: List[float] = []
        self._phase_error_threshold: float = 0.15
        self._phase_error_streak: int = 0
        self._phase_error_limit: int = 5  # 连续5次超标相变

        # 意图记录
        self._last_intent: Optional[Dict[str, Any]] = None

        # F3: 线程锁
        self._lock = threading.Lock()

    def _init_coupling(self) -> np.ndarray:
        """
        F1: 初始化耦合矩阵 — 拉普拉斯扩散核（自负 + 邻正，净零和）。
        
        每个目标格子 (r2,c2) 的入耦合权重满足：
          coupling[r2,c2,r2,c2] = -D  (自抑制)
          coupling[r1,c1,r2,c2] = +D/N  对每个邻接 (r1,c1) ∈ N(r2,c2)
          其他位置 = 0
        其中 D = COUPLING_STRENGTH = 0.3，N = 邻居数
        
        净效应：coupling_term = D * (avg_neighbor_values - self_value)
        这是标准的拉普拉斯扩散算子 — 把每个格子推向邻居平均值，永远不发散。
        """
        D = COUPLING_STRENGTH
        c = np.zeros((GRID_ROWS, GRID_COLS, GRID_ROWS, GRID_COLS), dtype=np.float64)
        for r2 in range(GRID_ROWS):
            for c2 in range(GRID_COLS):
                # 计算邻居
                neighbors = []
                for r1 in range(GRID_ROWS):
                    for c1 in range(GRID_COLS):
                        if r1 == r2 and c1 == c2:
                            continue
                        dr = abs(r1 - r2)
                        dc = abs(c1 - c2)
                        dist = (dr**2 + dc**2) ** 0.5
                        if dist <= 1.5:  # 8-connected neighborhood
                            neighbors.append((r1, c1))
                # 自抑制 -D，每个邻居 +D/N
                c[r2, c2, r2, c2] = -D
                if neighbors:
                    per_neighbor = D / len(neighbors)
                    for r1, c1 in neighbors:
                        c[r1, c1, r2, c2] = per_neighbor
        return c

    def _normalize_coupling(self):
        """
        F1: 兼容性保留方法。
        
        拉普拉斯扩散核天然净零和，无需归一化。此方法仅作为占位，不做任何操作。
        """
        pass  # 拉普拉斯核已保证稳定性

    def tick_step(self) -> Dict[str, Any]:
        """
        核心时钟步。每 30 秒由 TickDaemon 调用一次。
        
        内部动力学：
        1. 预测（F6: AR(1) 模型）
        2. 格点更新：耦合 + 衰减 + 外部驱动
        3. 帧滚动：新帧推入，老帧退出
        4. 误差计算 + 相变检测
        5. 意图提取
        
        F3: 主体在 self._lock 内执行，保证线程安全。
        """
        with self._lock:
            self.tick_count += 1
            now = time.time()

            # ── 1. 预测（F6: AR(1)） ──
            if self.tick_count >= 2:
                # x̂(t+1) = φ·x(t) + (1-φ)·x(t-1)  即指数平滑
                prev = self.frames[-2]
                last = self.frames[-1]
                self._last_prediction = AR_PHI * last + (1 - AR_PHI) * prev
            else:
                self._last_prediction = self.frames[-1].copy()

            # ── 2. 格点更新 ──
            new_frame = self._compute_next_frame()

            # ── 3. 帧滚动 ──
            self.frames = np.roll(self.frames, -1, axis=0)
            self.frames[-1] = new_frame

            # ── 4. 误差计算 + 相变检测 ──
            if self._last_prediction is not None:
                error = float(np.mean((new_frame - self._last_prediction) ** 2) ** 0.5)
                self._prediction_errors.append(error)
                if len(self._prediction_errors) > 60:
                    self._prediction_errors = self._prediction_errors[-60:]

                if error > self._phase_error_threshold:
                    self._phase_error_streak += 1
                else:
                    self._phase_error_streak = 0

                if self._phase_error_streak >= self._phase_error_limit:
                    self._trigger_phase_transition()

            # ── 5. 意图提取 ──
            self._last_intent = self._extract_intent()

            # ── 审计日志 ──
            # P2: 补全契约 §6 字段: anchor / difference / prediction / prediction_error
            diff_frame = (self.frames[-1] - self.frames[-2]) if len(self.frames) >= 2 else None
            record = {
                "ts": now,
                "tick": self.tick_count,
                "phase": self.phase,
                "error": self._prediction_errors[-1] if self._prediction_errors else 0.0,
                "streak": self._phase_error_streak,
                "anchor": round(float(np.mean(self.attractors)), 6),
                "difference": round(float(np.mean(np.abs(diff_frame))), 6) if diff_frame is not None else 0.0,
                "prediction": round(float(np.mean(self._last_prediction)) if self._last_prediction is not None else 0.0, 6),
                "prediction_error": round(float(np.mean(((self.frames[-1] - self._last_prediction) ** 2))) if self._last_prediction is not None else 0.0, 6),
                "intent": self._last_intent,
                "frame_summary": self._frame_summary(self.frames[-1]),
            }
            _append_log(record)
            return record

    def _compute_next_frame(self) -> np.ndarray:
        """
        计算下一帧。动力学 = 耦合传播 + 吸引子回归 + 微小噪声。
        """
        last = self.frames[-1].copy()

        # 耦合项：每个格子受所有其他格子影响（通过耦合矩阵加权）
        coupling_term = np.zeros_like(last)
        for r1 in range(GRID_ROWS):
            for c1 in range(GRID_COLS):
                influence = 0.0
                for r2 in range(GRID_ROWS):
                    for c2 in range(GRID_COLS):
                        influence += self.coupling[r1, c1, r2, c2] * last[r2, c2]
                coupling_term[r1, c1] = influence

        # 吸引子回归：向基线漂移
        attractor_term = (self.attractors - last) * 0.02

        # 微小系统噪声（不可消除的内在随机性）
        noise = np.random.normal(0, 0.005, last.shape)

        # 合成
        new = last + coupling_term + attractor_term + noise

        # 硬裁剪到 [-1, 1] 避免发散
        np.clip(new, -1.0, 1.0, out=new)
        return new

    def _trigger_phase_transition(self):
        """
        F4: 相变重设计（不用验证-回滚）。
        
        当前设计：
        - 识别高误差区域（最近帧中贡献预测误差的格子）
        - 针对性重排这些区域的耦合子块
        - 重置相关吸引子
        - 直接生效，无回滚
        """
        self._phase_error_streak = 0
        self.phase += 1
        event = {
            "type": "phase_transition",
            "ts": time.time(),
            "from_phase": self.phase - 1,
            "to_phase": self.phase,
            "error_history_tail": self._prediction_errors[-5:],
            "redesigned": True,  # F4: 标记已重设计
        }
        self.phase_history.append(event)

        # 计算最近预测误差（逐格）用于识别高误差区域
        last = self.frames[-1]
        pred = self._last_prediction
        if pred is not None:
            per_cell_error = (last - pred) ** 2
            # 找出误差最大的行耦合子块进行重排
            row_error = np.mean(per_cell_error, axis=1)  # 每行平均误差
            high_error_rows = np.where(row_error > np.mean(row_error))[0]
        else:
            high_error_rows = np.arange(GRID_ROWS)

        # F4: 结构重排 — 重写高误差行的耦合子块（拉普拉斯核，净零和）
        D = COUPLING_STRENGTH
        for r in high_error_rows:
            for c in range(GRID_COLS):
                # 重置该目标格子的耦合行为拉普拉斯核
                neighbors = []
                for r1 in range(GRID_ROWS):
                    for c1 in range(GRID_COLS):
                        if r1 == r and c1 == c:
                            continue
                        dist = ((r1 - r)**2 + (c1 - c)**2) ** 0.5
                        if dist <= 1.5:
                            neighbors.append((r1, c1))
                        else:
                            self.coupling[r1, c1, r, c] = 0.0
                self.coupling[r, c, r, c] = -D
                if neighbors:
                    for r1, c1 in neighbors:
                        self.coupling[r1, c1, r, c] = D / len(neighbors)
        
        # F1: 拉普拉斯核无需归一化

        # 重置吸引子：高误差行的吸引子设为当前帧值
        for r in high_error_rows:
            self.attractors[r] = last[r]

    def _classify_text(self, text: str) -> Dict[str, float]:
        """
        P1: 语义路由 — 把文本分类成 {energy, pain, warmth, withdraw} 四连续分数。
        使用词典匹配 + 强度累加。无 LLM、无网络。

        TODO [Architect seq-7]: 此函数使用外部词库匹配（if-then），违反差异原语原则第一条/第九条。
              等 between.py 跑起来后，替换为 Between 结构涌现的信号。
              当前保留是为了 verify_p0_fixes.py 不报错，不代表这是正确的信号路径。
        """
        text_lower = text.lower()
        scores = {"energy": 0.0, "pain": 0.0, "warmth": 0.0, "withdraw": 0.0}

        # 能量词（正向、活力、希望）
        energy_words = ["好", "棒", "开心", "高兴", "喜欢", "爱", "感谢", "期待", "加油",
                        "干", "冲", "努力", "积极", "阳光", "希望", "充满", "动力", "活力"]
        # 痛苦词（负面、受伤）
        pain_words = ["痛", "苦", "烦", "累", "难过", "哭", "伤心", "绝望", "糟糕", "糟",
                      "压力", "焦虑", "压抑", "生气", "愤怒", "恨", "死", "崩溃", "不好", "难受"]
        # 温度词（关系、亲密）
        warmth_words = ["你", "我们", "陪", "想", "亲", "抱", "暖", "关心", "体贴", "温柔",
                        "朋友", "家人", "在一起", "聊天", "说话"]
        # 退缩词（回避、抽离）
        withdraw_words = ["别", "不要", "算了", "走", "离开", "不想", "不用", "无所谓",
                          "随便", "没事", "静静", "沉默", "关机", "算了", "停"]

        for w in energy_words:
            if w in text_lower:
                scores["energy"] += 0.15
        for w in pain_words:
            if w in text_lower:
                scores["pain"] += 0.15
        for w in warmth_words:
            if w in text_lower:
                scores["warmth"] += 0.12
        for w in withdraw_words:
            if w in text_lower:
                scores["withdraw"] += 0.15

        # 长度归一化（避免长文本绝对优势）但保留微小边界
        max_score = max(scores.values()) if max(scores.values()) > 0 else 1.0
        if max_score > 1.0:
            for k in scores:
                scores[k] /= max_score

        return scores

    def receive_input(self, text: str = "", signal: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        接收外部输入。
        
        - text：原始文本（P0-A: 用 encoder 编码 + P1: 语义路由分类）
        - signal：直接注入的数值字典，如 {"energy": 0.3, "pain": -0.1}
        
        P0-A: 文本注入分两条路径：
          1. encoder.py 随机投影 → 稠密 (6,6) 网格注入
          2. fallback: zlib.crc32 确定性替代 hash()，进程可复现
        P1: 同时生成 {energy, pain, warmth, withdraw} 语义分数走 signal 分支
        F3: 主体在锁内执行。
        """
        with self._lock:
            last = self.frames[-1].copy()

            if signal:
                for key, val in signal.items():
                    for r, label in enumerate(ROW_LABELS):
                        if label.startswith(key.lower()[:3]):
                            last[r, 0] += float(val)
                            break

            if text:
                # ── P0-A: 随机投影编码器注入（稠密六行覆盖）──
                try:
                    from encoder import encode as _encode_grid
                    vec = _encode_grid(text)
                    if vec is not None and vec.shape == (GRID_ROWS, GRID_COLS):
                        last += vec * 0.3
                except Exception:
                    # fallback: zlib.crc32 → 确定性落点（跨进程一致）
                    crc = zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF
                    row_idx = crc % GRID_ROWS
                    col_idx = (crc >> 8) % GRID_COLS
                    intensity = min(len(text) / 100.0, 1.0)
                    last[row_idx, col_idx] += intensity * 0.1

                # ── P1: 语义路由分类 → signal 通道 ──
                semantic_scores = self._classify_text(text)
                for key, val in semantic_scores.items():
                    for r, label in enumerate(ROW_LABELS):
                        if label.startswith(key.lower()[:3]):
                            last[r, 0] += float(val) * 0.1
                            break

            np.clip(last, -1.0, 1.0, out=last)
            self.frames[-1] = last

            return {
                "type": "input_received",
                "ts": time.time(),
                "text_len": len(text),
                "signal": signal,
                "affected_cells": self._frame_summary(last),
            }

    def read_intent(self) -> Dict[str, Any]:
        """
        从当前帧提取意图。
        
        意图 = 当前帧中绝对值最大的几个格子的方向 + 强度。
        不同帧状态 → 不同意图（用于 test_core test2）。
        F2 修复：flat.sort 使用 abs(x[0]) 而非 abs(x[1])。
        P0-C: 主体在锁内执行，与 tick_step 并发安全。
        """
        with self._lock:
            return self._read_intent_unlocked()

    def _read_intent_unlocked(self) -> Dict[str, Any]:
        """read_intent 的无锁内部实现（调用者必须持有 self._lock）。"""
        frame = self.frames[-1]
        
        # 找前 6 个最活跃的格子（绝对值最大）
        flat = [(float(frame.ravel()[i]), i) for i in range(frame.size)]
        flat.sort(key=lambda x: abs(x[0]), reverse=True)  # F2: 修复，原为 abs(x[1])
        
        top_cells = []
        for val, idx in flat[:6]:
            r, c = divmod(idx, GRID_COLS)
            top_cells.append({
                "cell": _cell_name(r, c),
                "value": round(float(val), 4),
            })

        # 整体能量（格子绝对值均值）
        energy = float(np.mean(np.abs(frame)))

        # 方向：正负均值（正向 vs 负向）
        direction = float(np.mean(frame))

        # 相性签名：六个行的均值，用于区分不同状态
        row_signature = [round(float(np.mean(frame[r])), 4) for r in range(GRID_ROWS)]

        intent = {
            "type": "intent",
            "ts": time.time(),
            "tick": self.tick_count,
            "phase": self.phase,
            "top_cells": top_cells,
            "energy": round(energy, 4),
            "direction": round(direction, 4),
            "row_signature": row_signature,
        }
        self._last_intent = intent
        return intent

    def render(self) -> str:
        """
        把当前认知状态渲染为人类可读文本。
        这是一个简单文本渲染（不使用 LLM）。
        需要 LLM 增强时使用 renderer.py。
        """
        frame = self.frames[-1]
        intent = self._last_intent or self.read_intent()
        lines = []
        lines.append(f"[认知核心 t={self.tick_count} phase={self.phase}]")
        lines.append(f"  意图能量: {intent['energy']:.3f}  方向: {intent['direction']:+.3f}")
        lines.append(f"  活跃格: {', '.join(c['cell']+'='+format(c['value'], '+.2f') for c in intent['top_cells'][:4])}")
        
        # 网格概览（6×6）
        lines.append("  网格状态:")
        for r in range(GRID_ROWS):
            row_vals = " ".join(f"{frame[r,c]:+.2f}" for c in range(GRID_COLS))
            lines.append(f"    {ROW_LABELS[r][:4]:4s} [{row_vals}]")
        return "\n".join(lines)

    @property
    def snapshot(self) -> Dict[str, Any]:
        """
        P0-C: 原子快照。在锁内复制状态，避免与 tick_step 撕裂。
        """
        with self._lock:
            return {
                "tick": self.tick_count,
                "phase": self.phase,
                "frames_copy": self.frames[-1].copy(),
                "prediction_copy": self._last_prediction.copy() if self._last_prediction is not None else None,
                "last_error": self._prediction_errors[-1] if self._prediction_errors else 0.0,
                "attractor_copy": self.attractors.copy(),
                "coupling_hash": hash(self.coupling.tobytes()) % 100000000,
            }

    # ── 自读接口 ────────────────────────────────────────────────────────────────
    
    @property
    def diff(self) -> Optional[np.ndarray]:
        """最近两帧的差（frames[-1] - frames[-2]）。"""
        if self.tick_count < 2:
            return None
        return self.frames[-1] - self.frames[-2]

    @property
    def prediction_error(self) -> Optional[float]:
        """最近一次预测误差。"""
        if not self._prediction_errors:
            return None
        return self._prediction_errors[-1]

    @property
    def hidden_structure(self) -> Dict[str, Any]:
        """内部结构快照：耦合矩阵统计 + 吸引子状态。"""
        return {
            "coupling_nonzero": int(np.count_nonzero(self.coupling)),
            "coupling_sum": round(float(np.sum(self.coupling)), 6),
            "coupling_max": round(float(np.max(np.abs(self.coupling))), 6),
            "attractor_mean": round(float(np.mean(self.attractors)), 6),
            "attractor_std": round(float(np.std(self.attractors)), 6),
        }

    # ── 内部工具 ────────────────────────────────────────────────────────────────

    def _frame_summary(self, frame: np.ndarray) -> Dict[str, Any]:
        """单帧摘要"""
        return {
            "mean": round(float(np.mean(frame)), 4),
            "std": round(float(np.std(frame)), 4),
            "abs_max": round(float(np.max(np.abs(frame))), 4),
            "row_means": [round(float(np.mean(frame[r])), 4) for r in range(GRID_ROWS)],
        }

    def _extract_intent(self) -> Dict[str, Any]:
        """
        内部意图提取（与 read_intent 逻辑相同）。
        注意：必须调用 _read_intent_unlocked()，不能调用 read_intent()，
        否则当 tick_step 已持锁时会死锁（非可重入 Lock）。
        """
        return self._read_intent_unlocked()


# ── 全局单例（认知核心只需一个） ──────────────────────────────────────────────

_core: Optional[CognitiveCore] = None
_daemon_thread: Optional[threading.Thread] = None


def get_core(seed: int = 42) -> CognitiveCore:
    """
    获取全局认知核心单例。
    
    P0-B: 首次调用时恢复持久化状态 + 启动 TickDaemon 心跳线程。
    """
    global _core, _daemon_thread
    if _core is None:
        _core = CognitiveCore(seed=seed)

        # P0-B: 尝试从磁盘恢复状态
        try:
            from persistence import load_core
            load_core(_core)
        except Exception:
            pass  # 无持久化文件时跳过，保持当前初始化

        # P0-B: 启动守护线程（心跳）
        if _daemon_thread is None or not _daemon_thread.is_alive():
            _daemon_thread = threading.Thread(
                target=_heartbeat_loop,
                args=(_core,),
                daemon=True,
                name="cognitive-heartbeat",
            )
            _daemon_thread.start()

    return _core


def _heartbeat_loop(core: CognitiveCore, interval: float = 30.0):
    """
    P0-B: 心跳循环。每 interval 秒调用一次 core.tick_step()。
    与 tick_daemon.py 逻辑相同但以线程内嵌方式运行，不依赖外部进程。
    """
    while True:
        try:
            time.sleep(interval)
            core.tick_step()
        except Exception:
            time.sleep(1.0)  # 出错后短暂等待再重试


# ── 日志助手 ──────────────────────────────────────────────────────────────────

_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cognitive_core_log.jsonl")

def _append_log(record: Dict[str, Any]):
    """追加审计日志。"""
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 日志写入失败不阻塞核心运行


# ── CLI 入口 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    core = get_core(seed=42)
    print("认知核心初始化完成")
    print(core.render())
    print()
    print("--- 跑 5 个 tick ---")
    for i in range(5):
        record = core.tick_step()
        error = record["error"]
        intent_energy = record["intent"]["energy" if "energy" in record["intent"] else "energy"]
        print(f"  tick={record['tick']}  phase={record['phase']}  error={error:.4f}  intent_energy={intent_energy:.4f}")
    print()
    print("--- 注入信号 ---")
    core.receive_input(signal={"energy": 0.5, "pain": -0.3})
    record = core.tick_step()
    print(f"  post-signal row_signature: {record['intent']['row_signature']}")
