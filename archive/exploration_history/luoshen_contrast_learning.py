#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP191 - luoshen_contrast_learning.py
==================================================
洛神对比学习模块：
定义 16 个基础对比词（大/小/多/少/长/短/宽/窄/高/低/重/轻/满/空/紧/松）
的 16x16 参考矩阵，将磁盘使用率与时间间隔转为当前状态矩阵，
计算当前状态与每个对比词的相似度，选出 top1/top2，
并在词库内部两两比较找出最相似的一对词（most_similar_pair），
从而理解"像"的关系。

依赖: hashlib, json, time, re
仅允许:
  - 写入 perception_input/luoshen_contrast_learning.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型

相似度: sim = 1 - MAD/255，越大越相似。
扩展说明:
  1) 扩展对比词库：在 CONTRAST_WORDS 中新增 16x16 的 0~255 矩阵即可自动参与比较；
  2) 调整相似度方法：替换 similarity()（如余弦/相关系数），仅需返回 0~1 相似值；
  3) 扩展当前状态矩阵：修改 build_space_matrix / build_time_matrix，保持
     "与数据正相关、16x16、0~255" 约束。
"""

import hashlib
import json
import re
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
SPACE_LOG = "spatial_awareness_log.jsonl"
TIME_LOG = "time_gap_log.jsonl"
OUTPUT_FILE = "perception_input/luoshen_contrast_learning.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

META_FIELDS = {"timestamp", "schema_version", "source"}

SIZE = 16
WHITE = 240
DARK = 40


# ----------------------------------------------------------------------
# 基础对比词库：16 个词的 16x16 参考矩阵（0~255）
# ----------------------------------------------------------------------
def _fill_all(v):
    return [[v for _ in range(SIZE)] for _ in range(SIZE)]


def _gen_big():
    """大：整体灰度偏高且分布广。"""
    return _fill_all(190)


def _gen_small():
    """小：整体灰度偏低且分布集中。"""
    m = [[210 for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(5, 11):
        for j in range(5, 11):
            m[i][j] = DARK
    return m


def _gen_many():
    """多：矩阵中高值点密集。"""
    m = [[50 for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(SIZE):
            if i % 2 == 0 and j % 2 == 0:
                m[i][j] = 220
    return m


def _gen_few():
    """少：矩阵中高值点稀疏。"""
    m = [[180 for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(SIZE):
            if i % 4 == 0 and j % 4 == 0:
                m[i][j] = DARK
    return m


def _gen_long():
    """长：矩阵沿横向连续延伸（前 14 列暗带）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(14):
            m[i][j] = DARK
    return m


def _gen_short():
    """短：矩阵沿横向集中（中央 4 列暗块）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(6, 10):
            m[i][j] = DARK
    return m


def _gen_wide():
    """宽：矩阵横向延展明显（前 13 列暗带，横向几乎贯穿）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(13):
            m[i][j] = DARK
    return m


def _gen_narrow():
    """窄：矩阵横向收窄（中央 2 列暗带）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(SIZE):
        for j in range(7, 9):
            m[i][j] = DARK
    return m


def _gen_high():
    """高：矩阵纵向延展明显（前 14 行暗带）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(14):
        for j in range(SIZE):
            m[i][j] = DARK
    return m


def _gen_low():
    """低：矩阵纵向压缩（中央 4 行暗带）。"""
    m = [[WHITE for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(6, 10):
        for j in range(SIZE):
            m[i][j] = DARK
    return m


def _gen_heavy():
    """重：矩阵整体灰度偏低且致密。"""
    return _fill_all(DARK)


def _gen_light():
    """轻：矩阵整体灰度偏高且疏散。"""
    return _fill_all(205)


def _gen_full():
    """满：矩阵边缘和中心均被填满。"""
    return _fill_all(30)


def _gen_empty():
    """空：矩阵中心区域大面积留白。"""
    m = [[30 for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(6, 10):
        for j in range(6, 10):
            m[i][j] = 255
    return m


def _gen_tight():
    """紧：矩阵高值区域间距小（高频细密明暗交替）。"""
    m = []
    for i in range(SIZE):
        row = []
        for j in range(SIZE):
            row.append(200 if (i + j) % 2 == 0 else 60)
        m.append(row)
    return m


def _gen_loose():
    """松：矩阵高值区域间距大（大块亮斑居中，四周留空）。"""
    m = [[40 for _ in range(SIZE)] for _ in range(SIZE)]
    for i in range(3, 13):
        for j in range(3, 13):
            m[i][j] = 200
    return m


CONTRAST_WORDS = {
    "大": _gen_big(),
    "小": _gen_small(),
    "多": _gen_many(),
    "少": _gen_few(),
    "长": _gen_long(),
    "短": _gen_short(),
    "宽": _gen_wide(),
    "窄": _gen_narrow(),
    "高": _gen_high(),
    "低": _gen_low(),
    "重": _gen_heavy(),
    "轻": _gen_light(),
    "满": _gen_full(),
    "空": _gen_empty(),
    "紧": _gen_tight(),
    "松": _gen_loose(),
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
    空间状态矩阵：磁盘使用率越高，矩阵整体越暗、越致密（越接近重/满/紧）。
    规则：基准灰度 avg = 255*(1 - fill)，叠加确定性扰动。
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
            v = avg + ((i * 5 + j * 11) % 7) - 3
            row.append(max(0, min(255, v)))
        m.append(row)
    return m


def build_time_matrix(time_seconds):
    """
    时间状态矩阵：时间间隔越长，矩阵横向暗色连续带越长（越接近长/宽）。
    规则：col = round(16 * clamp(0.3 + t/30000, 0, 1))，前 col 列暗，其余亮。
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
# 相似度：逐像素平均绝对差 -> 归一化相似度（0~1）
# ----------------------------------------------------------------------
def similarity(a, b):
    total = 0
    for i in range(SIZE):
        for j in range(SIZE):
            total += abs(a[i][j] - b[i][j])
    mad = total / float(SIZE * SIZE)
    return round(1.0 - mad / 255.0, 4)


def top2_adjectives(matrix):
    """返回当前矩阵相似度最高的两个词及其相似度。"""
    ranked = sorted(
        ((similarity(matrix, ref), word) for word, ref in CONTRAST_WORDS.items()),
        reverse=True,
    )
    top1_sim, top1_word = ranked[0]
    top2_sim, top2_word = ranked[1]
    return top1_word, top1_sim, top2_word, top2_sim


def most_similar_pair_in_library():
    """在词库内部两两比较，找出相似度最高的一对词。"""
    words = list(CONTRAST_WORDS.keys())
    best_pair = None
    best_sim = -1.0
    for i in range(len(words)):
        for j in range(i + 1, len(words)):
            sim = similarity(CONTRAST_WORDS[words[i]], CONTRAST_WORDS[words[j]])
            if sim > best_sim:
                best_sim = sim
                best_pair = [words[i], words[j]]
    return best_pair, best_sim


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

    space_top1, space_top1_sim, space_top2, space_top2_sim = top2_adjectives(space_matrix)
    time_top1, time_top1_sim, time_top2, time_top2_sim = top2_adjectives(time_matrix)
    pair, pair_sim = most_similar_pair_in_library()

    record = {
        "schema_version": 2,
        "timestamp": ts,
        "space_precise": disk_percent if disk_percent is not None else "未获取",
        "space_top1": space_top1,
        "space_top1_sim": space_top1_sim,
        "space_top2": space_top2,
        "space_top2_sim": space_top2_sim,
        "time_precise": time_seconds if time_seconds is not None else "未获取",
        "time_top1": time_top1,
        "time_top1_sim": time_top1_sim,
        "time_top2": time_top2,
        "time_top2_sim": time_top2_sim,
        "most_similar_pair": pair,
        "pair_similarity": pair_sim,
        "source": "luoshen_contrast_learning",
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(record, ensure_ascii=False))

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
