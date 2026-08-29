#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 上下文临时存储模块 context_cache.py"""
import hashlib
import json
import time

DIALOG = "用户：我觉得洛神应该能记住一些关键的东西，而不是什么都记。\n洛神：你是说像人一样，只记几个重要的点？\n用户：对，比如咱们聊过什么，哪个点好玩，我当时想干嘛。"


def main():
    try:
        # 2.2 生成上下文临时存储记录
        timestamp = time.time()
        record = {
            "schema_version": 1,
            "timestamp": timestamp,
            "context_text": DIALOG,
            "expire_at": timestamp + 2592000,
            "reminded": False,
        }

        # 2.3 追加写入 context_cache.jsonl
        with open('context_cache.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.4 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('context_cache.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records = [json.loads(ln) for ln in chain_lines]
        prev_hash = records[-1].get("record_hash") if records else None
        ts = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(ts)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": ts,
            "file": "context_cache.jsonl",
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
