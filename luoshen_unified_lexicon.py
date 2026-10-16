#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP210
luoshen_unified_lexicon.py

目标：把大模型教学内容（llm_teaching_batch1.jsonl）中的汉字记录与洛神已有的
视觉矩阵挂接，生成统一联合词库 luoshen_unified_lexicon.jsonl，使每个汉字同时
具备视觉（matrix）、拼音（pinyin）、语义标签（tags）、形近字（similar）等多维信息。

视觉矩阵优先级：simple_char_matrix > hanzi_visual_map > hanzi_visual_map_batch2 > internal_symbol_visual_map
同一字符在多个文件中出现时，仅保留最高优先级来源的矩阵。

依赖：hashlib、json、time（Python 3.10+）
仅允许：创建 luoshen_unified_lexicon.py、luoshen_unified_lexicon.jsonl、追加 hash_chain_v2.log
禁止：修改已有文件、使用绝对路径、调用外部大模型
"""
import hashlib
import json
import time

# 视觉矩阵文件及各自取键字段，按优先级从高到低排列
MATRIX_SOURCES = [
    ("perception_input/simple_char_matrix.jsonl", "char"),
    ("perception_input/hanzi_visual_map.jsonl", "hanzi"),
    ("perception_input/hanzi_visual_map_batch2.jsonl", "hanzi"),
    ("perception_input/internal_symbol_visual_map.jsonl", "symbol"),
]

TEACHING_PATH = "perception_input/llm_teaching_batch1.jsonl"
OUT_PATH = "perception_input/luoshen_unified_lexicon.jsonl"
CHAIN_LOG = "hash_chain_v2.log"


def load_matrix_map():
    """按优先级建立 symbol -> matrix 映射。

    遍历文件时若键已存在（已被更高优先级来源占用）则跳过，保证
    simple_char_matrix 优先于其它文件。matrix 均直接引用已有文件内容，不新造。
    """
    mat = {}
    for path, key in MATRIX_SOURCES:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                sym = d.get(key)
                if sym is not None and sym not in mat:
                    mat[sym] = d["matrix"]
    return mat


def load_hanzi_records():
    """读取教学词库，仅提取 type=hanzi 的记录。"""
    records = []
    with open(TEACHING_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("type") == "hanzi":
                records.append(d)
    return records


def is_valid_matrix(m):
    """校验 matrix 是否为 16x16、元素 0~255 的二维列表。"""
    if not isinstance(m, list) or len(m) != 16:
        return False
    for row in m:
        if not isinstance(row, list) or len(row) != 16:
            return False
        for v in row:
            if not isinstance(v, int) or not (0 <= v <= 255):
                return False
    return True


def build_unified(records, mat):
    """为每条 hanzi 记录生成联合记录；未找到矩阵的汉字跳过不生成。"""
    unified = []
    unmatched = 0
    for r in records:
        content = r.get("content", {})
        ch = content.get("char")
        if ch is None:
            unmatched += 1
            continue
        matrix = mat.get(ch)
        if matrix is None or not is_valid_matrix(matrix):
            unmatched += 1
            continue
        unified.append({
            "schema_version": 2,
            "timestamp": time.time(),
            "char": ch,
            "pinyin": content.get("pinyin", ""),
            "tags": content.get("tags", []),
            "similar": content.get("similar", ""),
            "matrix": matrix,
            "source": "luoshen_unified_lexicon",
        })
    return unified, unmatched


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_chain_tail(chain_file):
    """读取哈希链最后一条记录的 record_hash 作为本次 prev_hash。"""
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
    """按 v2 公式追加一条哈希链记录：record_hash = md5(file_hash + prev_hash + str(ts))"""
    ts = time.time()
    file_hash = md5_of_file(target_file)
    record_hash = hashlib.md5(
        "{}{}{}".format(file_hash, prev_hash, str(ts)).encode("utf-8")).hexdigest()
    entry = {"schema_version": 2, "timestamp": ts, "file": target_file,
             "file_hash": file_hash, "prev_hash": prev_hash, "record_hash": record_hash}
    with open(chain_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def main():
    mat = load_matrix_map()
    records = load_hanzi_records()
    unified, unmatched = build_unified(records, mat)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in unified:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("unified=%d" % len(unified))
    print("unmatched=%d" % unmatched)

    prev_hash = read_chain_tail(CHAIN_LOG)
    entry = append_hash_chain(CHAIN_LOG, OUT_PATH, prev_hash)
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
