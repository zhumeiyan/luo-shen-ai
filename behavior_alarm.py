#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 行为报警模块 behavior_alarm.py"""
import hashlib
import json
import time


def main():
    try:
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = f.readlines()
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        # 2.2 模拟报警事件
        alarm_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "event_type": "suspicious_write",
            "source": "unknown",
            "target": "hospital_rules/principles.json",
            "intent": "modify",
            "description": "检测到尝试修改核心规则文件的写操作",
        }

        # 2.4 追加写入 behavior_alarm.jsonl
        with open('behavior_alarm.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(alarm_record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        with open('behavior_alarm.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records = []
        for line in chain_lines:
            line = line.strip()
            if line:
                records.append(json.loads(line))

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
            "file": "behavior_alarm.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        print(json.dumps(alarm_record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
