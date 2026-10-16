#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 内在状态快照模块 luoshen_state_snapshot.py

功能：
    整合已有的自我报告、符号连接和概念理解结果，并附加当前哈希链
    链尾状态，生成一条"洛神当前状态快照"，写入
    perception_input/luoshen_state_snapshot.jsonl。

快照内容：
    - self_report        ：自我报告全文（来自 luoshen_self_report.jsonl 末条）
    - symbol_link_sample ：符号连接示例（来自 internal_symbol_link_result.jsonl 首条）
    - concept_sample     ：概念理解示例（来自 concept_understand_result.jsonl 末条）
    - chain_tail         ：哈希链链尾 record_hash
    - chain_length       ：哈希链总行数

扩展方式：
    未来新增快照维度，只需在 SNAPSHOT_SOURCES 中登记
    (字段名, 数据文件, 提取方式说明)，并按注释模板新增一个提取函数，
    在 build_snapshot() 中调用即可，无需修改哈希链逻辑。
"""
import hashlib
import json
import time

RESULT_FILE = "perception_input/luoshen_state_snapshot.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

SELF_REPORT_FILE = "perception_input/luoshen_self_report.jsonl"
SYMBOL_LINK_FILE = "perception_input/internal_symbol_link_result.jsonl"
CONCEPT_FILE = "perception_input/concept_understand_result.jsonl"


def load_last_record(path):
    """读取数据文件最后一条有效记录；文件不存在或为空返回 None"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    return json.loads(lines[-1])


def load_first_record(path):
    """读取数据文件第一条有效记录；文件不存在或为空返回 None"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    return json.loads(lines[0])


def extract_self_report(path):
    """提取自我报告全文：取末条记录的 report 字段"""
    rec = load_last_record(path)
    if rec is None:
        return ""
    return str(rec.get("report", ""))


def extract_symbol_link_sample(path):
    """提取符号连接示例：取首条记录的 char/sense/summary"""
    rec = load_first_record(path)
    if rec is None:
        return ""
    return "char=%s, sense=%s, summary=%s" % (
        rec.get("char", ""), rec.get("sense", ""), rec.get("summary", ""))


def extract_concept_sample(path):
    """提取概念理解示例：取末条记录的 understanding"""
    rec = load_last_record(path)
    if rec is None:
        return ""
    return str(rec.get("understanding", ""))


def read_chain_state(path):
    """读取哈希链链尾 record_hash 与总行数"""
    tail_hash = ""
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            count += 1
            tail_hash = json.loads(line)["record_hash"]
    return tail_hash, count


def build_snapshot():
    """构建洛神当前状态快照字典"""
    self_report = extract_self_report(SELF_REPORT_FILE)
    symbol_sample = extract_symbol_link_sample(SYMBOL_LINK_FILE)
    concept_sample = extract_concept_sample(CONCEPT_FILE)
    chain_tail, chain_length = read_chain_state(CHAIN_FILE)
    return {
        "schema_version": 2,
        "timestamp": time.time(),
        "self_report": self_report,
        "symbol_link_sample": symbol_sample,
        "concept_sample": concept_sample,
        "chain_tail": chain_tail,
        "chain_length": chain_length,
        "source": "luoshen_state_snapshot",
    }


def append_chain(path, prev_hash):
    """为指定文件计算 md5 并按 v2 公式追加一条哈希链记录，返回新 record_hash"""
    with open(path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    timestamp = time.time()
    record_hash = hashlib.md5(
        (file_hash + prev_hash + str(timestamp)).encode("utf-8")
    ).hexdigest()
    with open(CHAIN_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "schema_version": 2,
            "timestamp": timestamp,
            "file": path,
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }, ensure_ascii=False) + "\n")
    print("file=%s" % path)
    print("file_hash=%s" % file_hash)
    print("prev_hash=%s" % prev_hash)
    print("record_hash=%s" % record_hash)
    print("timestamp=%s" % timestamp)
    return record_hash


def main():
    snap = build_snapshot()

    # 写入结果文件（创建/覆盖本结果文件）
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")

    # 控制台打印完整快照记录
    print("=== 洛神当前状态快照 ===")
    print(json.dumps(snap, ensure_ascii=False))

    # 哈希链追加（仅一条：luoshen_state_snapshot.jsonl）
    prev_hash = read_chain_state(CHAIN_FILE)[0]
    print("=== 哈希链追加 ===")
    append_chain(RESULT_FILE, prev_hash)


if __name__ == "__main__":
    main()
