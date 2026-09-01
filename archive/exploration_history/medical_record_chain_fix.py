#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 内部病历本指纹补链模块 medical_record_chain_fix.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取 treatment_apply_log.jsonl 并计算 md5
        try:
            with open('treatment_apply_log.jsonl', 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            print(json.dumps({"error": "treatment_apply_log.jsonl not found"}))
            return

        # 2.2 读取 hash_chain_v2.log 最后一条记录的 record_hash
        try:
            records = []
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        prev_hash = None
        if records:
            prev_hash = records[-1].get("record_hash")

        # 2.3 生成新哈希链记录
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "treatment_apply_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        # 2.4 追加写入 hash_chain_v2.log
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.5 标准输出
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
