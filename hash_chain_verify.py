#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 哈希链完整性验证模块 hash_chain_verify.py"""
import hashlib
import json
import sys
import time


def main():
    try:
        with open('hash_chain.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(json.dumps({"error": "hash_chain.log not found"}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)

    try:
        records = []
        for line in lines:
            line = line.strip()
            if line:
                records.append(json.loads(line))

        current_hash = hashlib.md5(open('physical_state.jsonl', 'rb').read()).hexdigest()

        if not records:
            verify_result = "empty_chain"
            last_hash = None
            current_hash_out = None
        else:
            last_hash = records[-1].get("hash")
            if last_hash == current_hash:
                verify_result = "ok"
            else:
                verify_result = "chain_broken"
            current_hash_out = current_hash

        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "verify_result": verify_result,
            "last_hash": last_hash,
            "current_hash": current_hash_out,
        }

        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
