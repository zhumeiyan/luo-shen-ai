#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 会话时间间隔感知模块 time_gap_awareness.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 检查 time_gap_log.jsonl 是否存在
        try:
            with open('time_gap_log.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            lines = []

        if not lines:
            gap_seconds = 0
            gap_message = "首次运行"
        else:
            last_record = json.loads(lines[-1])
            last_time = last_record.get("timestamp", 0)
            gap_seconds = time.time() - last_time
            gap_message = f"{gap_seconds:.0f}秒前"

        # 2.2 生成时间间隔记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "gap_seconds": gap_seconds,
            "gap_message": gap_message,
            "source": "time_gap_awareness",
        }

        # 2.3 追加写入 time_gap_log.jsonl
        with open('time_gap_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.4 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('time_gap_log.jsonl', 'rb') as f:
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
            "file": "time_gap_log.jsonl",
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
