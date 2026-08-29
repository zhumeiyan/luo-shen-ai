#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 第三批词汇教学模块 teach_symbols_batch3.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义本批教学内容
        teachings = [
            ("\u25c7", "闲"),  # ◇ -> 闲
            ("\u2606", "静"),  # ☆ -> 静
        ]
        taught_by = "朱美岩"

        # 2.2/2.3 生成记忆记录并追加写入 self_word_memory.jsonl
        records = []
        for symbols, words in teachings:
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "symbols": symbols,
                "words": words,
                "taught_by": taught_by,
                "source": "self_word_memory",
            }
            records.append(record)

        with open('self_word_memory.jsonl', 'a', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.4 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('self_word_memory.jsonl', 'rb') as f:
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
            "file": "self_word_memory.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.5 标准输出
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
