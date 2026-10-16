#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP213: luoshen_attention_glasses.py
为形近字生成注意力热点矩阵：比较形近字时，先关注关键差异区域。

依赖：hashlib、json、time
只读矩阵来源（相对路径）：
  - perception_input/hanzi_matrix_llm_batch1.jsonl  (char)
  - perception_input/simple_char_matrix.jsonl       (char)
  - perception_input/hanzi_visual_map.jsonl         (hanzi)
  - perception_input/hanzi_visual_map_batch2.jsonl  (hanzi)
  - perception_input/luoshen_unified_lexicon.jsonl  (char)
  - perception_input/hanzi_master_learned.jsonl     (char, 前序步骤生成的矩阵来源)
产出：
  - perception_input/luoshen_attention_hotspots.jsonl
上链：追加 hash_chain_v2.log 一条（v2 公式，针对 hotspots 文件）

算法：
  1. 读取所有矩阵来源文件，建立 char -> 第一个矩阵 的映射。
  2. 目标字：日、目、白、田、由、甲；缺失字跳过，至少保留 日、目、白、田。
  3. 相邻字对：日-目、目-白、白-田、田-由、由-甲。
  4. 对每对两端均存在的字对，计算 16x16 逐像素绝对差矩阵。
  5. 对每个字，聚合所有包含它的字对差异矩阵，逐像素取平均 -> 注意力热点矩阵(0~255)。
  6. 每条记录: {"schema_version":2, "timestamp":..., "char":字,
                "attention_matrix":16x16热点矩阵, "source":"luoshen_attention_glasses"}

扩展说明：
  - 新增形近字：把字加入 TARGET_CHARS，并保证其矩阵存在于某个 MATRIX_FILES 来源。
  - 调整热点计算方法：修改 PAIRS（相邻字对）或热点聚合方式（目前逐像素均值，
    可改为加权求和/取最大值，见 aggregate_hotspots）。
"""
import hashlib
import json
import time

MATRIX_FILES = [
    ("perception_input/hanzi_matrix_llm_batch1.jsonl", "char"),
    ("perception_input/simple_char_matrix.jsonl", "char"),
    ("perception_input/hanzi_visual_map.jsonl", "hanzi"),
    ("perception_input/hanzi_visual_map_batch2.jsonl", "hanzi"),
    ("perception_input/luoshen_unified_lexicon.jsonl", "char"),
    ("perception_input/hanzi_master_learned.jsonl", "char"),
]
OUT = "perception_input/luoshen_attention_hotspots.jsonl"
CHAIN = "hash_chain_v2.log"
SOURCE = "luoshen_attention_glasses"
SCHEMA = 2

# 目标形近字（缺失字自动跳过）
TARGET_CHARS = ["日", "目", "白", "田", "由", "甲"]
# 相邻字对（差异矩阵来源）
PAIRS = [("日", "目"), ("目", "白"), ("白", "田"), ("田", "由"), ("由", "甲")]


def md5hex(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def is_hanzi(ch):
    return len(ch) == 1 and "\u4e00" <= ch <= "\u9fff"


def load_matrix_map():
    """读取所有矩阵来源，返回 char -> 第一个矩阵（16x16）的映射"""
    m = {}
    for path, key in MATRIX_FILES:
        try:
            lines = open(path, encoding="utf-8").read().strip().splitlines()
        except FileNotFoundError:
            print("[skip] missing file:", path)
            continue
        for line in lines:
            r = json.loads(line)
            ch = r.get(key)
            if isinstance(ch, str):
                ch = ch.strip()
            if not is_hanzi(ch) or ch in m:
                continue
            mat = r.get("matrix")
            if not mat or len(mat) != 16 or len(mat[0]) != 16:
                continue
            m[ch] = mat
    return m


def abs_diff_matrix(a, b):
    """逐像素绝对差 -> 16x16 差异矩阵"""
    return [[abs(va - vb) for va, vb in zip(ra, rb)] for ra, rb in zip(a, b)]


def aggregate_hotspots(char, matrix_map, pairs):
    """对指定字，综合所有包含它的相邻字对差异矩阵，逐像素取平均。
    返回 16x16 热点矩阵(0~255 整数)。"""
    diffs = []
    for ca, cb in pairs:
        if char not in (ca, cb):
            continue
        if ca not in matrix_map or cb not in matrix_map:
            continue
        diffs.append(abs_diff_matrix(matrix_map[ca], matrix_map[cb]))
    n = len(diffs)
    h, w = 16, 16
    if n == 0:
        return None
    hotspot = [[0] * w for _ in range(h)]
    for i in range(h):
        for j in range(w):
            total = sum(d[i][j] for d in diffs)
            hotspot[i][j] = round(total / n)
    return hotspot


def summarize(hotspot):
    """热点矩阵摘要：平均强度、最大强度位置（0-based 行/列）"""
    total = 0
    cnt = 0
    mx = -1
    pos = None
    for i, row in enumerate(hotspot):
        for j, v in enumerate(row):
            total += v
            cnt += 1
            if v > mx:
                mx = v
                pos = (i, j)
    return round(total / cnt, 2), mx, pos


def main():
    matrix_map = load_matrix_map()
    # 目标字按顺序，缺失字跳过
    present = [ch for ch in TARGET_CHARS if ch in matrix_map]
    print("[STEP213] present target chars:", ",".join(present))
    missing = [ch for ch in TARGET_CHARS if ch not in matrix_map]
    if missing:
        print("[STEP213] skipped missing chars:", ",".join(missing))

    records = []
    for ch in present:
        hotspot = aggregate_hotspots(ch, matrix_map, PAIRS)
        if hotspot is None:
            print("[STEP213] char %s has no adjacent diff, skip" % ch)
            continue
        avg, mx, pos = summarize(hotspot)
        print(
            "[STEP213] %s avg_strength=%s max_strength=%d max_pos=(%d,%d)"
            % (ch, avg, mx, pos[0], pos[1])
        )
        records.append(
            {
                "schema_version": SCHEMA,
                "timestamp": time.time(),
                "char": ch,
                "attention_matrix": hotspot,
                "source": SOURCE,
            }
        )

    with open(OUT, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("[STEP213] written", OUT, "records =", len(records))

    with open(OUT, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    print("[STEP213] file_md5 =", file_hash)

    # 哈希链追加（仅一条）
    chain_lines = open(CHAIN, encoding="utf-8").read().strip().splitlines()
    prev_hash = json.loads(chain_lines[-1])["record_hash"]
    ts = time.time()
    record_hash = md5hex(file_hash + prev_hash + str(ts))
    entry = {
        "schema_version": SCHEMA,
        "timestamp": ts,
        "file": OUT,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("[STEP213] prev_hash =", prev_hash)
    print("[STEP213] record_hash =", record_hash)


if __name__ == "__main__":
    main()
