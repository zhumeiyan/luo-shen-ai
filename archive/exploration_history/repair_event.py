#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 修复事件记录模块 repair_event.py"""
import hashlib
import json
import time


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return [json.loads(line) for line in lines]


def main():
    try:
        # 2.1 生成一条修复事件记录
        repair_event = {
            "schema_version": 1,
            "timestamp": time.time(),
            "action": "treatment_apply",
            "source": "self",
            "repair_id": "repair_001",
        }

        # 2.2 追加写入 repair_events.jsonl
        with open('repair_events.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(repair_event, ensure_ascii=False) + '\n')

        # 2.3 计算 md5 并追加哈希链
        with open('repair_events.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            records = load_chain_records('hash_chain_v2.log')
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        prev_hash = None
        if records:
            prev_hash = records[-1].get("record_hash")

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "repair_events.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.4 标准输出
        print(json.dumps(repair_event, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
