#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 事件日志哈希链补录 event_log_chain_update_v2.py"""
import hashlib
import json
import time


def main():
    try:
        try:
            with open('event_log.jsonl', 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            print(json.dumps({"error": "event_log.jsonl not found"}))
            return

        prev_hash = None
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if lines:
                last_record = json.loads(lines[-1])
                prev_hash = last_record.get("record_hash")
        except FileNotFoundError:
            prev_hash = None

        timestamp = 1724832000
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "event_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
