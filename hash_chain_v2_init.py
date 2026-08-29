#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 新哈希链初始化模块 hash_chain_v2_init.py"""
import hashlib
import json
import sys
import time


def main():
    try:
        with open('physical_state.jsonl', 'rb') as f:
            file_content = f.read()
    except FileNotFoundError:
        print(json.dumps({"error": "physical_state.jsonl not found"}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)

    try:
        file_hash = hashlib.md5(file_content).hexdigest()

        prev_hash = None
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                lines = f.readlines()
            records = []
            for line in lines:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
            if records:
                prev_hash = records[-1].get("record_hash")
        except FileNotFoundError:
            pass

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "physical_state.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(chain_record, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
