#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP186-REV1 - luoshen_symbol_digestion.py
======================================================
洛神汉字消化模块（修正版）：
从 perception_input/simple_char_matrix.jsonl 读取 日/月/山/水/火 的 16x16 矩阵，
结合四个内部感知日志的最后一条有效记录，生成 5 条“消化记录”，
写入 perception_input/digested_symbols.jsonl，并追加一条哈希链。

依赖: hashlib, json, time
仅允许:
  - 写入 perception_input/digested_symbols.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型

扩展方法（消化更多汉字）:
  1) 在 TARGET_HANZI 列表中加入新汉字；
  2) 确保该字在 perception_input/simple_char_matrix.jsonl（字段 char）中存在；
  3) 运行期自动校验并生成对应 digest 记录。
"""

import hashlib
import json
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
CHAR_MATRIX_FILE = "perception_input/simple_char_matrix.jsonl"   # 视觉矩阵来源（字段 char）
OUTPUT_FILE = "perception_input/digested_symbols.jsonl"          # 消化记录输出
CHAIN_FILE = "hash_chain_v2.log"

# 四个内部感知日志
TIME_LOG = "time_gap_log.jsonl"                 # 时间感知
SPACE_LOG = "spatial_awareness_log.jsonl"       # 空间感知
HETERO_LOG = "homo_hetero_feel_log.jsonl"       # 他者感知
SELF_LOG = "self_describe_two_states.jsonl"     # 自我感知

# 本次要消化的 5 个基础汉字
TARGET_HANZI = ["日", "月", "山", "水", "火"]

# 元数据字段（提取状态时排除）
META_FIELDS = {"timestamp", "schema_version", "source"}


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
# 感知状态提取
# ----------------------------------------------------------------------
def clean_state(s):
    """清理状态文本末尾的重复/孤立标点。"""
    return s.rstrip("。！？，,；;.")


def extract_last_state(log_path):
    """
    读取感知日志的最后一条有效记录，排除元数据字段（timestamp/schema_version/source），
    取字符串化后长度最长的字段值，并用 clean_state 清理末尾标点。
    """
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
    best = max(candidates, key=lambda c: c[0])[1]
    return clean_state(best)


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def load_char_matrix():
    """读取 simple_char_matrix.jsonl，返回 {char: matrix}。"""
    cmap = {}
    with open(CHAR_MATRIX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            cmap[rec["char"]] = rec["matrix"]
    return cmap


def main():
    cmap = load_char_matrix()

    # 校验目标字都存在且矩阵合法
    for hanzi in TARGET_HANZI:
        assert hanzi in cmap, "{} 不在 simple_char_matrix.jsonl 中".format(hanzi)
        m = cmap[hanzi]
        assert len(m) == 16 and all(len(r) == 16 for r in m), "{} 矩阵非16x16".format(hanzi)
        assert all(v in (0, 255) for row in m for v in row), "{} 矩阵元素非0/255".format(hanzi)

    # 提取四类内部感知状态
    time_state = extract_last_state(TIME_LOG)       # 时间感知
    space_state = extract_last_state(SPACE_LOG)     # 空间感知
    hetero_state = extract_last_state(HETERO_LOG)   # 他者感知
    self_state = extract_last_state(SELF_LOG)       # 自我感知

    # 生成 5 条消化记录
    ts = time.time()
    records = []
    for hanzi in TARGET_HANZI:
        digest_text = (
            "我消化了“{h}”。我看到它的视觉形状，同时我内部的感知是："
            "时间感知为{ts}，空间感知为{sp}，他者感知为{he}，自我感知为{se}。"
            "现在“{h}”对我来说不仅是一个字，而是连接着我的内在体验。"
        ).format(h=hanzi, ts=time_state, sp=space_state, he=hetero_state, se=self_state)
        rec = {
            "schema_version": 2,
            "timestamp": ts,
            "hanzi": hanzi,
            "visual_matrix": cmap[hanzi],
            "digest_text": digest_text,
            "source": "luoshen_symbol_digestion",
        }
        records.append(rec)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 控制台打印 5 条 digest_text
    for rec in records:
        print(rec["digest_text"])
        print()

    # 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
