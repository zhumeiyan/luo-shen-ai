#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 概念理解模块 concept_understander.py

功能：
    读取 internal_symbol_link_result.jsonl 中已有的抽象字符号连接结果
    （字-感知来源-感知数据摘要），为每个抽象字生成"理解结果"，
    输出 "字-感知-理解" 的结构化结果到
    perception_input/concept_understand_result.jsonl。

扩展方式：
    未来新增抽象字，只需在 internal_symbol_linker.py 的 SYMBOL_TO_SENSE
    映射表中增加键值对并运行该模块；本模块自动处理
    internal_symbol_link_result.jsonl 中出现的所有记录，无需修改核心逻辑。
"""
import hashlib
import json
import time

LINK_FILE = "perception_input/internal_symbol_link_result.jsonl"
RESULT_FILE = "perception_input/concept_understand_result.jsonl"
CHAIN_FILE = "hash_chain_v2.log"


def load_link_results(path):
    """读取符号连接结果，返回记录列表；文件不存在或为空返回 []"""
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except FileNotFoundError:
        pass
    return records


def build_understanding(link):
    """根据连接结果生成理解内容。

    规则：
      - 若该字 summary 存在且非"无数据"，则
        understanding = "洛神对“{字}”的感知：{summary}"
      - 否则 understanding = "洛神暂未积累对“{字}”的内部感知"
    """
    char = link.get("char", "未知")
    summary = link.get("summary", "")
    if summary and summary != "无数据":
        return "洛神对“%s”的感知：%s" % (char, summary)
    return "洛神暂未积累对“%s”的内部感知" % char


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
    links = load_link_results(LINK_FILE)
    results = []
    for link in links:
        results.append({
            "schema_version": 2,
            "timestamp": time.time(),
            "char": link.get("char"),
            "sense": link.get("sense"),
            "module": link.get("module"),
            "understanding": build_understanding(link),
        })

    # 写入结果文件（创建/覆盖本结果文件）
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 控制台打印四条理解结果
    print("=== 概念理解结果 ===")
    for rec in results:
        print(json.dumps(rec, ensure_ascii=False))
    print("result_file=%s" % RESULT_FILE)

    # 哈希链追加（仅一条：concept_understand_result.jsonl）
    prev_hash = current_chain_tail()
    print("=== 哈希链追加 ===")
    append_chain(RESULT_FILE, prev_hash)


if __name__ == "__main__":
    main()
