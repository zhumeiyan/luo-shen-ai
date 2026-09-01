#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 日志哈希链更新模块 physical_sensor_step5.py"""
import hashlib
import json
import sys
import time


def main():
    try:
        with open('physical_state.jsonl', 'rb') as f:
            content = f.read()
    except FileNotFoundError:
        print(json.dumps({"error": "physical_state.jsonl not found"}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)

    try:
        file_hash = hashlib.md5(content).hexdigest()

        chain_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "file": "physical_state.jsonl",
            "hash": file_hash,
        }

        with open('hash_chain.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(chain_record, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
