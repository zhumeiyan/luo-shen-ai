#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 内部符号-感知桥接器 internal_symbol_linker.py

功能：
    将抽象汉字（时间/空间/他者/我）与其对应的内部感知日志数据桥接，
    输出 "字-感知来源-感知数据摘要" 的结构化结果到
    perception_input/internal_symbol_link_result.jsonl。

扩展方式：
    未来新增抽象字，只需在 SYMBOL_TO_SENSE 映射表中增加键值对
    (字 -> {module, data_file, sense})，无需修改任何核心逻辑。
"""
import hashlib
import json
import time

RESULT_FILE = "perception_input/internal_symbol_link_result.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

# 抽象字 -> 感知来源映射表。
# 新增抽象字只需在此增加键值对：{字: {"module":模块名, "data_file":日志, "sense":感知名}}
SYMBOL_TO_SENSE = {
    "时间": {"module": "time_gap_awareness", "data_file": "time_gap_log.jsonl", "sense": "时间感知"},
    "空间": {"module": "spatial_awareness", "data_file": "spatial_awareness_log.jsonl", "sense": "空间感知"},
    "他者": {"module": "homo_hetero_feel", "data_file": "homo_hetero_feel_log.jsonl", "sense": "他者感知"},
    "我":   {"module": "self_describe_two_states", "data_file": "self_describe_two_states.jsonl", "sense": "自我感知"},
}

# 元数据字段：提取摘要时排除，不视为感知数据内容
META_FIELDS = {"timestamp", "schema_version", "source"}


def load_last_record(path):
    """读取数据文件最后一条记录；文件不存在或为空返回 None"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    return json.loads(lines[-1])


def build_summary(record):
    """从最后一条记录提取最重要的一个字段值作为摘要。

    规则：排除 timestamp/schema_version/source 等元数据字段后，
    取字符串值最长的字段值作为摘要；若无可判断字段，则输出完整 JSON 字符串。
    """
    if record is None:
        return "无数据"
    candidates = {
        k: v for k, v in record.items() if k not in META_FIELDS
    }
    if candidates:
        # 取字段值字符串化后最长的那个作为"最重要字段"
        best_key = max(candidates, key=lambda k: len(str(candidates[k])))
        return str(candidates[best_key])
    return json.dumps(record, ensure_ascii=False)


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


def current_chain_tail():
    """读取哈希链当前链尾 record_hash；链空则返回空串"""
    prev_hash = ""
    with open(CHAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                prev_hash = json.loads(line)["record_hash"]
    return prev_hash


def main():
    results = []
    for char, info in SYMBOL_TO_SENSE.items():
        record = load_last_record(info["data_file"])
        summary = build_summary(record)
        results.append({
            "schema_version": 2,
            "timestamp": time.time(),
            "char": char,
            "sense": info["sense"],
            "module": info["module"],
            "summary": summary,
        })

    # 写入结果文件（创建/覆盖本结果文件）
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 控制台打印四条结果
    print("=== 内部符号-感知桥接结果 ===")
    for rec in results:
        print(json.dumps(rec, ensure_ascii=False))
    print("result_file=%s" % RESULT_FILE)

    # 哈希链追加（仅一条：internal_symbol_link_result.jsonl）
    prev_hash = current_chain_tail()
    print("=== 哈希链追加 ===")
    append_chain(RESULT_FILE, prev_hash)


if __name__ == "__main__":
    main()
