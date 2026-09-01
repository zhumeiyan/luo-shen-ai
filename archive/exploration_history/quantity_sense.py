#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 数量感分级模块 quantity_sense.py"""
import hashlib
import json
import time

PERCENT_NAMES = {"memory_percent", "disk_percent", "cpu_percent"}


def main():
    try:
        try:
            with open('numeric_self_scan.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "numeric_self_scan.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "numeric_self_scan.jsonl empty or not found"}))
            return
        numbers = json.loads(lines[-1]).get("numbers", [])

        records = []
        for item in numbers:
            name = item.get("name")
            value = item.get("value")

            if value is None:
                level = "unknown"
            elif name in PERCENT_NAMES:
                if value < 30:
                    level = "低"
                elif value < 60:
                    level = "中"
                elif value < 85:
                    level = "高"
                else:
                    level = "极高"
            else:
                if value <= 1:
                    level = "极少"
                elif value <= 5:
                    level = "少"
                elif value <= 20:
                    level = "中等"
                elif value <= 100:
                    level = "多"
                else:
                    level = "很多"

            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "name": name,
                "value": value,
                "level": level,
                "source": "quantity_sense",
            }
            records.append(record)

        # 2.4 追加写入 quantity_sense_log.jsonl
        with open('quantity_sense_log.jsonl', 'a', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('quantity_sense_log.jsonl', 'rb') as f:
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
            "file": "quantity_sense_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
