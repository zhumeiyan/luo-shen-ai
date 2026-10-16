#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 哈希链验证模块 hash_chain_verify_v3.py"""
import hashlib
import json
import sys
import time


def main():
    try:
        with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(json.dumps({"error": "hash_chain_v2.log not found"}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)

    try:
        with open('physical_state.jsonl', 'rb') as f:
            current_file_hash = hashlib.md5(f.read()).hexdigest()

        records = []
        for line in lines:
            line = line.strip()
            if line:
                records.append(json.loads(line))

        issues = []
        for idx, rec in enumerate(records):
            line_number = idx + 1
            prev_hash = rec.get("prev_hash")
            file_hash = rec.get("file_hash")
            timestamp = rec.get("timestamp")
            record_hash = rec.get("record_hash")

            if idx == 0:
                if prev_hash is not None:
                    issues.append({
                        "line_number": line_number,
                        "issue_type": "invalid_genesis",
                        "detail": "first record prev_hash is not null",
                    })
            else:
                if prev_hash != records[idx - 1].get("record_hash"):
                    issues.append({
                        "line_number": line_number,
                        "issue_type": "chain_broken",
                        "detail": "prev_hash does not match previous record_hash",
                    })

            join_prev = prev_hash if prev_hash else ""
            expected = hashlib.md5(
                (file_hash + join_prev + str(timestamp)).encode('utf-8')
            ).hexdigest()
            if expected != record_hash:
                issues.append({
                    "line_number": line_number,
                    "issue_type": "record_hash_mismatch",
                    "detail": "record_hash does not match recomputed value",
                })

        if records:
            last_file_hash = records[-1].get("file_hash")
            if last_file_hash != current_file_hash:
                issues.append({
                    "line_number": len(records),
                    "issue_type": "file_tampered",
                    "detail": "last file_hash does not match current physical_state.jsonl hash",
                })

        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chain_length": len(records),
            "chain_status": "ok" if not issues else "broken",
            "current_file_hash": current_file_hash,
            "issues": issues,
        }

        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
