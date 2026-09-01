#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP190 - luoshen_adjective_learning.py
==================================================
洛神形容词相似度学习模块：
定义 8 个基础形容词（轻/重/满/空/紧/松/长/短）的 16x16 参考矩阵，
将磁盘使用率与时间间隔转换为当前状态矩阵，
用逐像素平均绝对差（MAD）与基础感觉矩阵比较相似度，
选取最相似的基础形容词作为 learned_adjective，
写入 perception_input/luoshen_adjective_learning.jsonl，并追加一条哈希链记录。

依赖: hashlib, json, time, re
仅允许:
  - 写入 perception_input/luoshen_adjective_learning.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型

相似度定义:
  sim = 1 - MAD/255，范围 [0,1]，越大越相似；数据变化与所选形容词正相关。

扩展说明:
  1) 新增基础形容词：在 BASIC_SENSE_MATRIX 中追加一个 16 行 x 16 列的 0~255 列表，
     并在选词时自动纳入比较，无需改动其余逻辑；
  2) 调整当前状态矩阵生成：修改 build_space_matrix / build_time_matrix 的映射公式，
     保持"与数据正相关、尺寸 16x16、元素 0~255"三个约束即可；
  3) 更换相似度度量：替换 similarity 函数（如改为余弦相似度），仅需返回 0~1 的相似值。
"""

import hashlib
import json
import re
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
SPACE_LOG = "spatial_awareness_log.jsonl"   # 空间感知
TIME_LOG = "time_gap_log.jsonl"             # 时间感知
OUTPUT_FILE = "perception_input/luoshen_adjective_learning.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

META_FIELDS = {"timestamp", "schema_version", "source"}

SIZE = 16
WHITE = 240  # 亮区
DARK = 40    # 暗区

# ----------------------------------------------------------------------
# 基础感觉矩阵库：8 个基础形容词的 16x16 参考矩阵（0~255）
# ----------------------------------------------------------------------
def _fill_all(value):
    """生成全矩阵同值 16x16 矩阵。"""
    return [[value for _ in range(SIZE)] for _ in range(SIZE)]


def _gen_light():
    """轻：整体灰度偏高，分布均匀。"""
    return [[205 for _ in range(SIZE)] for _ in range(SIZE)]


def _gen_heavy():
    """重：整体灰度偏低，分布密集。"""
    return _fill_all(DARK)


def _gen_full():
    """满：矩阵边缘和中心都被填满。"""
    return [[30 for _ in range(SIZE)] for _ in range(SIZE)]


def _gen_empty():
    """空：矩阵中心区域空白较多。"""
    m = [[30 for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(6, 10):
        for j in range(6, 10):
            m[i][j] = 255
    return m


def _gen_tight():
    """紧：高灰度区域密集且间距小（高频细密棋盘）。"""
    m = []
    for i in range(SIZE):
        row = []
        for j in range(SIZE):
            row.append(200 if (i + j) % 2 == 0 else 60)
        m.append(row)
    return m


def _gen_loose():
    """松：高灰度区域分散且间距大（大块亮斑居中，四周留空）。"""
    m = [[40 for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(3, 13):
        for j in range(3, 13):
            m[i][j] = 200
    return m


def _gen_long():
    """长：沿横向连续分布（前 14 列连续暗带）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(14):
            m[i][j] = DARK
    return m


def _gen_short():
    """短：沿横向集中分布（中央 4 列集中暗块）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(6, 10):
            m[i][j] = DARK
    return m


BASIC_SENSE_MATRIX = {
    "轻": _gen_light(),
    "重": _gen_heavy(),
    "满": _gen_full(),
    "空": _gen_empty(),
    "紧": _gen_tight(),
    "松": _gen_loose(),
    "长": _gen_long(),
    "短": _gen_short(),
}


# ----------------------------------------------------------------------
# 通用工具
# ----------------------------------------------------------------------
def md5_of_file(path):
    """计算文件 md5（十六进制小写）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_chain_tail(chain_file):
    """读取哈希链最后一条记录的 record_hash。"""
    tail = None
    with open(chain_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("hash_chain_v2.log 无记录")
    return tail["record_hash"]


def append_hash_chain(chain_file, target_file, prev_hash):
    """按哈希链 v2 公式追加一条记录，只追加这一条。"""
    ts = time.time()
    file_hash = md5_of_file(target_file)
    raw = "{}{}{}".format(file_hash, prev_hash, str(ts))
    record_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()
    entry = {
        "schema_version": 2,
        "timestamp": ts,
        "file": target_file,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(chain_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def extract_last_state(log_path):
    """读取日志最后一条有效记录，排除元数据字段，取最长字段值。"""
    last = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    if last is None:
        raise RuntimeError("{} 无有效记录".format(log_path))

    candidates = []
    for k, v in last.items():
        if k in META_FIELDS:
            continue
        if isinstance(v, (str, int, float)):
            candidates.append((len(str(v)), str(v)))
    if not candidates:
        return ""
    return max(candidates, key=lambda c: c[0])[1]


def extract_disk_usage_percent(space_desc):
    """提取"磁盘已用 xx%"的百分比数值；未找到返回 None。"""
    m = re.search(r"磁盘已用\s*([0-9]+(?:\.[0-9]+)?)\s*%", space_desc)
    return float(m.group(1)) if m else None


def extract_time_seconds(time_desc):
    """提取时间状态描述中的第一个数值作为秒数；未找到返回 None。"""
    m = re.search(r"-?[0-9]+(?:\.[0-9]+)?", time_desc)
    return float(m.group(0)) if m else None


# ----------------------------------------------------------------------
# 当前状态矩阵生成（与数据正相关、确定性）
# ----------------------------------------------------------------------
def build_space_matrix(disk_percent):
    """
    空间矩阵：以磁盘使用率控制整体灰度。
    使用率越高 -> 矩阵整体越暗（越接近"重/满"）。
    生成规则：基准灰度 avg = 255*(1 - fill)，叠加确定性小扰动，保证 16x16、0~255。
    """
    if disk_percent is None:
        fill = 0.0
    else:
        fill = max(0.0, min(1.0, disk_percent / 100.0))
    avg = round(255 * (1.0 - fill))
    m = []
    for i in range(SIZE):
        row = []
        for j in range(SIZE):
            v = avg + ((i * 5 + j * 11) % 7) - 3  # 确定性扰动 [-3, +3]
            row.append(max(0, min(255, v)))
        m.append(row)
    return m


def build_time_matrix(time_seconds):
    """
    时间矩阵：以时间长短控制沿横向的连续长度。
    时间越长 -> 暗色横向连续带越长（越接近"长"）。
    生成规则：col = round(16 * clamp(0.3 + t/30000, 0, 1))，前 col 列暗，其余亮。
    """
    if time_seconds is None:
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, 0.3 + time_seconds / 30000.0))
    col = int(round(SIZE * ratio))
    col = max(0, min(SIZE, col))
    m = []
    for i in range(SIZE):
        row = []
        for j in range(SIZE):
            row.append(DARK if j < col else WHITE)
        m.append(row)
    return m


# ----------------------------------------------------------------------
# 相似度：逐像素平均绝对差 -> 归一化相似度（0~1，越大越相似）
# ----------------------------------------------------------------------
def similarity(a, b):
    total = 0
    for i in range(SIZE):
        for j in range(SIZE):
            total += abs(a[i][j] - b[i][j])
    mad = total / float(SIZE * SIZE)
    return round(1.0 - mad / 255.0, 4)


def best_adjective(matrix):
    """返回 (最佳形容词, 最佳相似度)。"""
    best_word = None
    best_sim = -1.0
    for word, ref in BASIC_SENSE_MATRIX.items():
        sim = similarity(matrix, ref)
        if sim > best_sim:
            best_sim = sim
            best_word = word
    return best_word, best_sim


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    ts = time.time()

    space_desc = extract_last_state(SPACE_LOG)
    time_desc = extract_last_state(TIME_LOG)
    disk_percent = extract_disk_usage_percent(space_desc)
    time_seconds = extract_time_seconds(time_desc)

    space_matrix = build_space_matrix(disk_percent)
    time_matrix = build_time_matrix(time_seconds)

    space_adj, space_sim = best_adjective(space_matrix)
    time_adj, time_sim = best_adjective(time_matrix)

    records = [
        {
            "schema_version": 2,
            "timestamp": ts,
            "dimension": "space",
            "precise": disk_percent if disk_percent is not None else "未获取",
            "learned_adjective": space_adj,
            "similarity": space_sim,
            "source": "luoshen_adjective_learning",
        },
        {
            "schema_version": 2,
            "timestamp": ts,
            "dimension": "time",
            "precise": time_seconds if time_seconds is not None else "未获取",
            "learned_adjective": time_adj,
            "similarity": time_sim,
            "source": "luoshen_adjective_learning",
        },
    ]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for rec in records:
        print(json.dumps(rec, ensure_ascii=False))

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
