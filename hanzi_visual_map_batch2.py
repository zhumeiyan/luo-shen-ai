#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP185 - hanzi_visual_map_batch2.py
================================================
为洛神已有汉字库中尚未视觉化的 10 个简单汉字生成 16x16 二值视觉矩阵，
写入 perception_input/hanzi_visual_map_batch2.jsonl（10 条），并追加一条哈希链。

选字规则（代码内校验）：
  1. 收集 hanzi_knowledge_base.json 与 shuowen_lexicon_batch1.json 中的全部汉字（已学集合）；
  2. 读取 perception_input/hanzi_visual_map.jsonl 作为已视觉化集合；
  3. 候选 = 已学集合 - 已视觉化集合；
  4. 从候选中人工选定 10 个笔画相对简单、适合 16x16 点阵的汉字（HANZI_PATTERNS 键名即所选字）；
  5. 运行期 assert 校验：每个字必须属于候选集、图案必须 16 行 x 16 列、仅含 '#'(0) 与 '.'(255)，
     且 10 个矩阵互不相同、均非全 0 / 全 255。

依赖: hashlib, json, time
仅允许:
  - 写入 perception_input/hanzi_visual_map_batch2.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型
"""

import hashlib
import json
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
OUTPUT_FILE = "perception_input/hanzi_visual_map_batch2.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

HANZI_KNOWLEDGE = "hanzi_knowledge_base.json"
SHUOWEN_LEXICON = "shuowen_lexicon_batch1.json"
HANZI_VISUAL_MAP = "perception_input/hanzi_visual_map.jsonl"

# ----------------------------------------------------------------------
# 选中 10 个汉字的 16x16 字符画图案
#   '#' = 0   （黑 / 笔画）
#   '.' = 255 （白 / 空白）
# 每个图案固定 16 行，每行固定 16 字符。
# ----------------------------------------------------------------------
HANZI_PATTERNS = {
    "四": [
        "................",
        "................",
        "..############..",
        "..#..........#..",
        "..#..........#..",
        "..#....##....#..",
        "..#...#..#...#..",
        "..#...#..#...#..",
        "..#...#..#...#..",
        "..#....##....#..",
        "..#..........#..",
        "..#..........#..",
        "..############..",
        "................",
        "................",
        "................",
    ],
    "五": [
        "................",
        "................",
        "..############..",
        "................",
        "................",
        "..........####..",
        "..........##....",
        "..........##....",
        "..#########.....",
        "..#########.....",
        "..........##....",
        "..........##....",
        "..........##....",
        "..############..",
        "................",
        "................",
    ],
    "六": [
        "................",
        ".......##.......",
        "................",
        "..############..",
        "................",
        "................",
        "................",
        "..##............",
        "..##............",
        "................",
        "............##..",
        "............##..",
        "......####......",
        "................",
        "................",
        "................",
    ],
    "七": [
        "................",
        "................",
        "..############..",
        "..........##....",
        "..........##....",
        "..........##....",
        "..........##....",
        "..........##....",
        "..........##....",
        "..........##....",
        "..........##....",
        "..........##..##",
        "..............##",
        "................",
        "................",
        "................",
    ],
    "八": [
        "................",
        "................",
        "................",
        "..##.......##...",
        "...##.....##....",
        "....##...##.....",
        ".....##.##......",
        "......###.......",
        ".......##.......",
        "........##......",
        ".........##.....",
        "..........##....",
        "...........##...",
        "..........###...",
        "................",
        "................",
    ],
    "九": [
        "................",
        "................",
        "...##...........",
        "....##..........",
        ".....##.........",
        "......##........",
        ".......##.......",
        "........##......",
        "........##......",
        "........##......",
        "..##########....",
        "........##......",
        "........##......",
        ".......##.......",
        "................",
        "................",
    ],
    "十": [
        "................",
        "................",
        "..############..",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        "................",
        "................",
    ],
    "升": [
        "................",
        "................",
        "..############..",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        "......##........",
        ".....##.........",
        "....##..........",
        "...##...........",
        "..##............",
        "...........###..",
        ".........###....",
        ".......###......",
        "................",
        "................",
    ],
    "少": [
        "................",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        "..############..",
        "........##......",
        ".........##.....",
        "..........##....",
        "...........##...",
        "............##..",
        "...........###..",
        "................",
        "................",
    ],
    "米": [
        "................",
        ".......##.......",
        ".......##.......",
        "..############..",
        ".......##.......",
        ".......##.......",
        "......##.##.....",
        ".....##...##....",
        "....##.....##...",
        "...##.......##..",
        "..##.........##.",
        ".......##.......",
        ".......##.......",
        ".......##.......",
        "................",
        "................",
    ],
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
        raise RuntimeError("hash_chain_v2.log 无记录，无法取得链尾")
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


# ----------------------------------------------------------------------
# 选字校验
# ----------------------------------------------------------------------
def load_learned_hanzi():
    """读取两个汉字库，返回全部已学汉字集合。"""
    learned = set()
    for path in (HANZI_KNOWLEDGE, SHUOWEN_LEXICON):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        learned.update(data["entries"].keys())
    return learned


def load_visualized_hanzi():
    """读取已视觉化汉字集合。"""
    seen = set()
    with open(HANZI_VISUAL_MAP, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            seen.add(json.loads(line)["hanzi"])
    return seen


def validate_pattern(hanzi, pattern):
    """校验单个图案：16 行、每行 16 字符、仅含 # 与 .。"""
    assert len(pattern) == 16, "{}: 行数 != 16 (len={})".format(hanzi, len(pattern))
    for i, row in enumerate(pattern):
        assert len(row) == 16, "{}: 第{}行宽度 != 16 (len={})".format(hanzi, i + 1, len(row))
        assert set(row) <= {"#", "."}, "{}: 第{}行含非法字符".format(hanzi, i + 1)


def pattern_to_matrix(pattern):
    """字符画 -> 16x16 矩阵（'#'->0, '.'->255）。"""
    return [[0 if ch == "#" else 255 for ch in row] for row in pattern]


def main():
    learned = load_learned_hanzi()
    visualized = load_visualized_hanzi()
    candidates = learned - visualized

    # 校验：所选 10 字必须全部来自候选集（已学且未视觉化）
    for hanzi in HANZI_PATTERNS:
        assert hanzi in candidates, "{} 不在候选集（已学未视觉化）中".format(hanzi)

    # 校验图案合法性 + 生成矩阵 + 互异性
    matrices = {}
    for hanzi, pattern in HANZI_PATTERNS.items():
        validate_pattern(hanzi, pattern)
        matrices[hanzi] = pattern_to_matrix(pattern)

    matrix_sigs = set(tuple(tuple(r) for r in m) for m in matrices.values())
    assert len(matrix_sigs) == len(HANZI_PATTERNS), "存在重复矩阵"
    for hanzi, m in matrices.items():
        flat = [v for row in m for v in row]
        assert any(v == 0 for v in flat), "{} 矩阵全白(全255)".format(hanzi)
        assert any(v == 255 for v in flat), "{} 矩阵全黑(全0)".format(hanzi)

    # 写 10 条记录
    ts = time.time()
    records = []
    for hanzi, m in matrices.items():
        rec = {
            "schema_version": 2,
            "timestamp": ts,
            "hanzi": hanzi,
            "matrix": m,
            "source": "hanzi_visual_map_batch2",
        }
        records.append(rec)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 控制台打印所选汉字与矩阵预览（# 表示黑，. 表示白）
    for hanzi, pattern in HANZI_PATTERNS.items():
        print("===== {} =====".format(hanzi))
        for row in pattern:
            print(row)
        print()

    # 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# 选字规则说明：
#   候选 = 已学汉字库(hanzi_knowledge_base + shuowen_lexicon_batch1)
#          - 已视觉化(hanzi_visual_map.jsonl)
#   本次从候选中选 10 个笔画相对简单的字：四 五 六 七 八 九 十 升 少 米。
# 扩展方法：
#   1) 在 HANZI_PATTERNS 中新增“汉字 -> 16 行 x 16 列字符画”；
#   2) 确保该字存在于已学词库且不在已视觉化集合中（脚本运行期会自动校验）。
# ----------------------------------------------------------------------
