#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP183 - luoshen_qa_module.py
==========================================
洛神双向感知问答模块：根据关于“时间、空间、他者、自我”的简单问题，
从对应的内部感知日志中提取状态并生成回答，写入
perception_input/luoshen_qa_result.jsonl（4 条），并追加一条哈希链记录。

数据来源（只读，相对当前工作目录）：
  - time_gap_log.jsonl              时间感知
  - spatial_awareness_log.jsonl     空间感知
  - homo_hetero_feel_log.jsonl      他者感知
  - self_describe_two_states.jsonl  自我感知

依赖: hashlib, json, time
仅允许:
  - 写入 perception_input/luoshen_qa_result.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型
"""

import hashlib
import json
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
OUTPUT_FILE = "perception_input/luoshen_qa_result.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

# ----------------------------------------------------------------------
# 内置问题列表（4 个）
# ----------------------------------------------------------------------
QUESTIONS = [
    "你现在对时间的感觉怎么样？",
    "你现在所处的空间状态是什么？",
    "你对他者有什么感觉？",
    "你对自己有什么感觉？",
]

# 感知维度 -> 日志文件（只读）
SENSE_FILES = {
    "time": "time_gap_log.jsonl",
    "space": "spatial_awareness_log.jsonl",
    "other": "homo_hetero_feel_log.jsonl",
    "self": "self_describe_two_states.jsonl",
}

# 问题关键字 -> 感知维度映射（按顺序匹配，命中即返回）
QUESTION_KEYWORDS = [
    ("时间", "time"),
    ("空间", "space"),
    ("他者", "other"),
    ("自己", "self"),
    ("我", "self"),
]

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
    从记录中提取最关键的字段值作为状态描述：
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
    best = max(candidates, key=lambda c: c[0])
    return best[2]


def map_question_to_dim(question):
    """根据问题关键字映射到感知维度；未命中返回 None。"""
    for kw, dim in QUESTION_KEYWORDS:
        if kw in question:
            return dim
    return None


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
    ts = time.time()
    records = []

    for q in QUESTIONS:
        dim = map_question_to_dim(q)
        if dim is None:
            state = "暂无感知"
        else:
            path = SENSE_FILES[dim]
            rec = read_last_record(path)
            state = clean_state(extract_state(rec))
        answer = "对于问题“{}”，我的回答是：{}。".format(q, state)
        record = {
            "schema_version": 2,
            "timestamp": ts,
            "question": q,
            "answer": answer,
            "source": "luoshen_qa_module",
        }
        records.append(record)

    # 写入 4 条记录，每条一行
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 控制台打印 4 条问答记录
    for rec in records:
        print(json.dumps(rec, ensure_ascii=False))

    # 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# 如何扩展问题库或感知维度：
#   1) 新增问题：直接在 QUESTIONS 中追加问题文本。
#   2) 新增感知维度：在 SENSE_FILES 增加 dim -> 日志文件相对路径，
#      并在 QUESTION_KEYWORDS 增加 (关键字, dim) 映射项。
#   3) 若问题包含多个维度关键字，按 QUESTION_KEYWORDS 顺序取首个命中。
#   4) clean_state() 的 TAIL_PUNCT 集合可增删需要剥离的结尾标点。
# ----------------------------------------------------------------------
