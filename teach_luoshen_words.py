#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神记词教学模块 teach_luoshen_words.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义本次教学内容
        symbols = "□ · ☀ ○"
        words = "空 轻 今 静"
        taught_by = "朱美岩"

        # 2.2 生成洛神自己的记忆记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "symbols": symbols,
            "words": words,
            "taught_by": taught_by,
            "source": "self_word_memory",
        }

        # 2.3 追加写入 self_word_memory.jsonl
        with open('self_word_memory.jsonl', 'a', encoding='utf-8') as f:
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

        records = [json.loads(ln) for ln in chain_lines]
        prev_hash = records[-1].get("record_hash") if records else None
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
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
