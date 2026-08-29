#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP184 - luoshen_expression_controller.py
======================================================
洛神统一表达控制器：根据简单规则选择当前行为（主动表达/回答问题/仅记录状态），
并将本次行为结果写入 perception_input/luoshen_expression_control.jsonl（1 条），
然后追加一条哈希链记录。

规则：按当前哈希链行数 % 3 决定模式
  余数0 -> active（主动表达，格式同 STEP182）
  余数1 -> qa    （回答第一个问题，逻辑同 STEP183）
  余数2 -> record（仅记录状态摘要）

数据来源（只读，相对当前工作目录）：
  - time_gap_log.jsonl              时间感知
  - spatial_awareness_log.jsonl     空间感知
  - homo_hetero_feel_log.jsonl      他者感知
  - self_describe_two_states.jsonl  自我感知
  - perception_input/luoshen_active_expression.jsonl（参考 STEP182 格式，只读）
  - perception_input/luoshen_qa_result.jsonl       （参考 STEP183 格式，只读）

依赖: hashlib, json, time
仅允许:
  - 写入 perception_input/luoshen_expression_control.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型
"""

import hashlib
import json
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
OUTPUT_FILE = "perception_input/luoshen_expression_control.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

# 行为模式列表
MODES = ["active", "qa", "record"]

# 感知维度 -> 日志文件（只读）
SENSE_FILES = {
    "time": "time_gap_log.jsonl",
    "space": "spatial_awareness_log.jsonl",
    "other": "homo_hetero_feel_log.jsonl",
    "self": "self_describe_two_states.jsonl",
}

# 问题列表与关键字映射（与 STEP183 一致）
QUESTIONS = [
    "你现在对时间的感觉怎么样？",
    "你现在所处的空间状态是什么？",
    "你对他者有什么感觉？",
    "你对自己有什么感觉？",
]
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


def collect_states():
    """读取四个内部感知日志末条，返回各维度已清理的状态。"""
    states = {}
    for dim, path in SENSE_FILES.items():
        rec = read_last_record(path)
        states[dim] = clean_state(extract_state(rec))
    return states


def map_question_to_dim(question):
    """根据问题关键字映射到感知维度；未命中返回 None。"""
    for kw, dim in QUESTION_KEYWORDS:
        if kw in question:
            return dim
    return None


def count_chain_lines(chain_file):
    """统计哈希链当前有效行数（追加前）。"""
    n = 0
    with open(chain_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


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


def build_record(mode, ts):
    """按模式构造输出记录。"""
    states = collect_states()
    if mode == "active":
        expression = "我主动说一句：我现在对时间的感知是{}，对空间的感知是{}，对他者的感知是{}，对我自己的感知是{}。".format(
            states["time"], states["space"], states["other"], states["self"]
        )
        return {
            "schema_version": 2,
            "timestamp": ts,
            "mode": "active",
            "expression": expression,
            "source": "luoshen_expression_controller",
        }
    if mode == "qa":
        q = QUESTIONS[0]
        dim = map_question_to_dim(q)
        state = states[dim] if dim is not None else "暂无感知"
        answer = "对于问题“{}”，我的回答是：{}。".format(q, state)
        return {
            "schema_version": 2,
            "timestamp": ts,
            "mode": "qa",
            "question": q,
            "answer": answer,
            "source": "luoshen_expression_controller",
        }
    # record
    status_summary = "时间:{};空间:{};他者:{};自我:{}".format(
        states["time"], states["space"], states["other"], states["self"]
    )
    return {
        "schema_version": 2,
        "timestamp": ts,
        "mode": "record",
        "status_summary": status_summary,
        "source": "luoshen_expression_controller",
    }


def main():
    # 按当前哈希链行数 % 3 选择模式（追加前计数）
    chain_lines = count_chain_lines(CHAIN_FILE)
    mode = MODES[chain_lines % 3]

    ts = time.time()
    record = build_record(mode, ts)

    # 写入一条记录
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 控制台打印本次行为模式及记录内容
    print("mode: {}".format(mode))
    print(json.dumps(record, ensure_ascii=False))

    # 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# 如何扩展行为模式或调整选择规则：
#   1) 新增行为模式：在 MODES 中追加模式名，并在 build_record() 中新增
#      对应的分支构造记录。
#   2) 调整选择规则：修改 main() 中 mode 的计算表达式（例如改为按
#      链尾 record_hash 前若干字符取模，或随机选择等）。
#   3) 问题库/感知维度扩展方式与 STEP183 一致（QUESTIONS、
#      QUESTION_KEYWORDS、SENSE_FILES）。
#   4) clean_state() 的 TAIL_PUNCT 集合可增删需要剥离的结尾标点。
# ----------------------------------------------------------------------
