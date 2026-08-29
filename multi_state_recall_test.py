#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 多状态回忆测试模块 multi_state_recall_test.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义四组模拟内部状态
        state_groups = [
            {"disk_percent": 90, "cost_per_day": 2.0, "gap_seconds": 100000, "cpu_percent": 60, "memory_percent": 55},
            {"disk_percent": 60, "cost_per_day": 0.01, "gap_seconds": 100, "cpu_percent": 20, "memory_percent": 30},
            {"disk_percent": 95, "cost_per_day": 0.01, "gap_seconds": 100, "cpu_percent": 20, "memory_percent": 30},
            {"disk_percent": 60, "cost_per_day": 2.0, "gap_seconds": 100000, "cpu_percent": 60, "memory_percent": 55},
        ]

        # 2.2 对每组状态生成内部符号串
        def build_symbols(s):
            sp = "\u2589" if s["disk_percent"] >= 80 else "\u25a1"
            en = "\uffe5" if s["cost_per_day"] > 1 else "\u00b7"
            tm = "\u263e" if s["gap_seconds"] > 86400 else "\u2600"
            bd = "\u25b3" if (s["cpu_percent"] >= 50 or s["memory_percent"] >= 50) else "\u25cb"
            return sp + " " + en + " " + tm + " " + bd

        symbols_list = [build_symbols(s) for s in state_groups]

        # 2.3 读取洛神自己的学习记忆文件
        memory_map = {}
        try:
            with open('self_word_memory.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            for ln in lines:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict) and "symbols" in rec and "words" in rec:
                        memory_map[rec["symbols"]] = rec["words"]
                except json.JSONDecodeError:
                    continue
        except FileNotFoundError:
            memory_map = {}

        # 2.4/2.5 生成测试记录并追加写入 multi_state_recall_log.jsonl
        records = []
        for symbols in symbols_list:
            if symbols in memory_map:
                words = memory_map[symbols]
                status = "learned"
            else:
                words = symbols
                status = "not_learned"
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "symbols": symbols,
                "words": words,
                "status": status,
                "source": "multi_state_recall_test",
            }
            records.append(record)

        with open('multi_state_recall_log.jsonl', 'a', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('multi_state_recall_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records_chain = [json.loads(ln) for ln in chain_lines]
        prev_hash = records_chain[-1].get("record_hash") if records_chain else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "multi_state_recall_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
