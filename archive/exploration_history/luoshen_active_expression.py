#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP182 - luoshen_active_expression.py
==================================================
洛神主动表达模块：根据内部感知状态主动生成一句表达，
写入 perception_input/luoshen_active_expression.jsonl，并追加一条哈希链记录。

数据来源（只读，相对当前工作目录）：
  - time_gap_log.jsonl          时间感知
  - spatial_awareness_log.jsonl 空间感知
  - homo_hetero_feel_log.jsonl  他者感知
  - self_describe_two_states.jsonl 自我感知

依赖: hashlib, json, time
仅允许:
  - 写入 perception_input/luoshen_active_expression.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型
"""

import hashlib
import json
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
OUTPUT_FILE = "perception_input/luoshen_active_expression.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

# 内部感知日志（维度 -> 文件，只读）
SENSE_FILES = {
    "time": "time_gap_log.jsonl",
    "space": "spatial_awareness_log.jsonl",
    "other": "homo_hetero_feel_log.jsonl",
    "self": "self_describe_two_states.jsonl",
}

# 元数据字段：不参与状态提取
META_FIELDS = {"timestamp", "schema_version", "source"}

# 结尾标点集合：clean_state 会去除状态末尾的这类标点与空白
TAIL_PUNCT = set("。！？!?；;，,.")


def clean_state(text):
    """去除状态文本末尾的多余空格与句号、感叹号、问号等结尾标点。"""
    if text is None:
        return ""
    s = str(text).strip()
    while s and (s[-1] in TAIL_PUNCT or s[-1].isspace()):
        s = s[:-1].rstrip()
    return s


def read_last_record(path):
    """读取 jsonl 最后一条有效记录；无数据返回 None。"""
    last = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                last = None
    return last


def extract_state(record):
    """
    从记录中提取最关键的字段值作为状态描述（与 STEP171 方法一致）：
      1. 排除 timestamp / schema_version / source 等元数据字段；
      2. 在剩余字段中，取字符串化后长度最长的字段值；
      3. 无数据时状态为“暂无感知”。
    """
    if record is None:
        return "暂无感知"
    candidates = []
    for key, value in record.items():
        if key in META_FIELDS:
            continue
        candidates.append((len(str(value)), key, str(value)))
    if not candidates:
        return "暂无感知"
    # 长度最长者胜出；并列时取首次出现者（max 保持稳定顺序）
    best = max(candidates, key=lambda c: c[0])
    return best[2]


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


def main():
    # 1) 读取四个内部感知日志的最后一条有效记录
    records = {}
    for dim, path in SENSE_FILES.items():
        records[dim] = read_last_record(path)

    # 2) 提取各维度状态描述并 3) 清理结尾标点
    state_time = clean_state(extract_state(records["time"]))
    state_space = clean_state(extract_state(records["space"]))
    state_other = clean_state(extract_state(records["other"]))
    state_self = clean_state(extract_state(records["self"]))

    # 4) 生成主动表达文本（状态后不加句号，整句只保留末尾一个句号）
    expression = "我主动说一句：我现在对时间的感知是{}，对空间的感知是{}，对他者的感知是{}，对我自己的感知是{}。".format(
        state_time, state_space, state_other, state_self
    )

    # 5) 写入一条记录
    record = {
        "schema_version": 2,
        "timestamp": time.time(),
        "expression": expression,
        "source": "luoshen_active_expression",
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 6) 控制台打印主动表达文本
    print(expression)

    # 7) 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# 如何扩展主动表达触发条件：
#   1) 在 SENSE_FILES 中增/删维度（dim -> 日志文件相对路径），新维度会自动
#      读取末条记录并纳入状态提取，无需改动主流程。
#   2) 若想调整“最关键时刻字段”的选取规则，修改 extract_state() 即可。
#   3) 若想改变表达模板，修改 main() 中 expression 的 format 字符串。
#   4) clean_state() 的 TAIL_PUNCT 集合可增删需要剥离的结尾标点。
# ----------------------------------------------------------------------
