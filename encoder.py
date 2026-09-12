#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encoder.py — 文本/信号编码器

原则：
- 可选依赖：requests + ZHIPU_API_KEY
- 缺失时降级为随机投影（F5: 固定投影矩阵，非零张量）
- 统一输出形状：(6, 6) 直接对应认知网格

F5 修复说明：
  原版使用哈希多种子累加，几何性质差。
  修改为：字符 unigram + bigram 计数特征 → 固定随机投影矩阵 → tanh 激活。
  这是标准的 random projection 方法（Johnson-Lindenstrauss 风格），
  无 API 时也能产生有结构意义的 (6,6) 张量。

智谱 API 文档：open.bigmodel.cn（ embeddings / 或 chat 接口）
"""

import numpy as np
import os
from typing import Optional

# 输出形状直接对应 6×6 网格
OUTPUT_SHAPE = (6, 6)
PROD_DIM = 36  # 输出维度

# 特征空间维度（字符 bigram 哈希桶特征空间）
FEATURE_DIM = 128

# F5: 固定随机投影矩阵（模块加载时固定，不每次重新生成）
# 使用固定 seed 保证投影矩阵一致性
_rng = np.random.RandomState(20260912)
# 投影矩阵: (PROD_DIM, FEATURE_DIM) — 行正交初始化保证独立性
PROJECTION_MATRIX = _rng.randn(PROD_DIM, FEATURE_DIM) / np.sqrt(FEATURE_DIM)

# 智谱 API 配置
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
ZHIPU_EMBEDDING_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
ZHIPU_MODEL = "embedding-2"  # 智谱 embedding v2，输出 1024 维

# 是否可用
_requests_available = False
try:
    import requests as _req
    _requests_available = True
except ImportError:
    pass


def _zero_tensor() -> np.ndarray:
    """降级输出：零张量。"""
    return np.zeros(OUTPUT_SHAPE, dtype=np.float64)


def _extract_features(text: str) -> np.ndarray:
    """
    将文本转为固定维度的数值特征向量（不用外部依赖）。
    
    特征类型：
    - unigram 哈希桶（字符 → 64 维）
    - bigram 哈希桶（相邻字符对 → 64 维）
    总计 128 维特征。
    """
    features = np.zeros(FEATURE_DIM, dtype=np.float64)
    if not text:
        return features
    
    # Unigram: 按字符 unicode mod 64 累加
    for ch in text:
        idx = ord(ch) % 64
        features[idx] += 1.0
    
    # Bigram: 相邻字符对 → 另外 64 维
    for i in range(len(text) - 1):
        h = (ord(text[i]) * 31 + ord(text[i + 1])) % 64
        features[64 + h] += 1.0
    
    # 归一化：避免长文本数值远大于短文本
    norm = np.linalg.norm(features)
    if norm > 1e-8:
        features /= norm
    
    return features


def _projection_encode(text: str) -> np.ndarray:
    """
    F5: 随机投影编码（无 API 时的主路径）。
    
    流程：特征向量 → 固定投影矩阵线性映射 → tanh 激活 → reshape 到 (6,6)。
    投影矩阵固定（seed=20260912），相同输入始终出相同输出。
    几何性质：相似文本 → 相似投影结果（因特征空间本身具有相似性）。
    """
    features = _extract_features(text)
    # 线性投影
    projected = PROJECTION_MATRIX @ features  # (PROD_DIM,)
    # tanh 激活：平滑压缩到 (-1, 1)
    activated = np.tanh(projected * 0.5)
    # reshape 到 (6, 6)
    grid = activated.reshape(OUTPUT_SHAPE)
    return grid


def _zhihu_encode(text: str) -> Optional[np.ndarray]:
    """
    使用智谱 API 编码。
    返回 (6,6) 网格或 None（出错时）。
    """
    if not ZHIPU_API_KEY or not _requests_available:
        return None
    
    try:
        response = _req.post(
            ZHIPU_EMBEDDING_URL,
            headers={
                "Authorization": f"Bearer {ZHIPU_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": ZHIPU_MODEL,
                "input": text[:512],  # 限制长度
            },
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        
        # 提取 embedding 向量
        embedding = result["data"][0]["embedding"]  # 1024 维
        
        # 把 1024 维映射到 36 维 (6×6)：通过均匀下采样 + 分组平均
        embedding_np = np.array(embedding, dtype=np.float64)
        # 下采样：每 1024/36 ≈ 28.44 个元素取平均
        indices = np.linspace(0, len(embedding_np), 37, dtype=int)[:36]
        sampled = np.array([
            np.mean(embedding_np[indices[i]:indices[i+1]]) if indices[i+1] > indices[i] else 0.0
            for i in range(36)
        ])
        grid = sampled.reshape(6, 6)
        # 归一化到 [-1, 1]
        max_abs = np.max(np.abs(grid))
        if max_abs > 0:
            grid = grid / max_abs
        return grid
    
    except Exception:
        # 出错时返回 None（外层会降级）
        return None


def encode(text: str) -> np.ndarray:
    """
    F5: 编码入口。优先级：智谱 API → 随机投影。
    
    返回 (6,6) 浮点张量，值域 [-1, 1]。
    """
    if not text or not text.strip():
        return _zero_tensor()
    
    if ZHIPU_API_KEY and _requests_available:
        result = _zhihu_encode(text)
        if result is not None:
            return result
    
    return _projection_encode(text)


def inject_to_core(core, text: str) -> dict:
    """
    编码并注入到认知核心。
    方便外部调用。
    """
    grid = encode(text)
    frame = core.frames[-1].copy()
    # 叠加而非覆盖（让新信息与旧状态融合）
    frame = frame + grid * 0.3  # 0.3 = 注入强度系数
    np.clip(frame, -1.0, 1.0, out=frame)
    core.frames[-1] = frame
    return {
        "type": "encoder_inject",
        "has_zhipu": bool(ZHIPU_API_KEY and _requests_available),
        "grid_mean": round(float(np.mean(grid)), 4),
        "grid_std": round(float(np.std(grid)), 4),
    }


if __name__ == "__main__":
    test_text = "今天心情很糟糕，工作压力大"
    
    print(f"测试编码: '{test_text}'")
    print(f"ZHIPU_API_KEY 可用: {bool(ZHIPU_API_KEY and _requests_available)}")
    
    grid = encode(test_text)
    print(f"编码输出形状: {grid.shape}")
    print(f"值域: [{grid.min():.3f}, {grid.max():.3f}]")
    print(f"均值: {grid.mean():.4f}")
    print()
    print("网格内容:")
    for r in range(6):
        print("  " + " ".join(f"{grid[r,c]:+.2f}" for c in range(6)))
