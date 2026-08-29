#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 数字变化感知模块 number_change_sense.py"""
import hashlib
import json
import time


def main():
    try:
        try:
            with open('numeric_self_scan.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "numeric_self_scan.jsonl not enough records"}))
            return
        if len(lines) < 2:
            print(json.dumps({"error": "numeric_self_scan.jsonl not enough records"}))
            return

        previous_record = json.loads(lines[-2])
        current_record = json.loads(lines[-1])
        previous_numbers = previous_record.get("numbers", [])
        current_numbers = current_record.get("numbers", [])

        prev_map = {}
        for item in previous_numbers:
            name = item.get("name")
            if name is not None:
                prev_map[name] = item.get("value")

        records = []
        for item in current_numbers:
            name = item.get("name")
            value = item.get("value")

            if name not in prev_map:
                change = "新增"
                prev_value = None
            elif value is None or prev_map[name] is None:
                change = "未知"
                prev_value = prev_map[name]
            elif value > prev_map[name]:
                change = "上升"
                prev_value = prev_map[name]
            elif value < prev_map[name]:
                change = "下降"
                prev_value = prev_map[name]
            else:
                change = "持平"
                prev_value = prev_map[name]

            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "name": name,
                "previous_value": prev_value,
                "current_value": value,
                "change": change,
                "source": "number_change_sense",
            }
            records.append(record)

        # 2.4 追加写入 number_change_log.jsonl
        with open('number_change_log.jsonl', 'a', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('number_change_log.jsonl', 'rb') as f:
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
            "file": "number_change_log.jsonl",
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
