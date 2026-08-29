#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 对话上下文自动缓存模块 context_cache_writer.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取最近一次对话记录
        try:
            with open('luoshen_main_v3_log.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "luoshen_main_v3_log.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "luoshen_main_v3_log.jsonl empty or not found"}))
            return

        last = json.loads(lines[-1])
        user_input = last.get("user_input", "")
        luoshen_reply = last.get("luoshen_reply", "")

        # 2.2 生成上下文缓存记录
        timestamp = time.time()
        record = {
            "schema_version": 1,
            "timestamp": timestamp,
            "user_input": user_input,
            "luoshen_reply": luoshen_reply,
            "expire_at": timestamp + 2592000,
            "reminded": False,
        }

        # 2.3 追加写入 conversation_context.jsonl
        with open('conversation_context.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.4 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('conversation_context.jsonl', 'rb') as f:
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
            "file": "conversation_context.jsonl",
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
