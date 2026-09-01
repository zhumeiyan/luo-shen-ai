#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 系统文件完整性监测模块 integrity_monitor.py"""
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
        records = []
        for line in lines:
            line = line.strip()
            if line:
                records.append(json.loads(line))

        # 2.1 验证链连续性
        chain_ok = True
        v2_records = [r for r in records if r.get("schema_version") == 2]
        for idx, rec in enumerate(v2_records):
            if idx == 0:
                if rec.get("prev_hash") is not None:
                    chain_ok = False
            else:
                if rec.get("prev_hash") != v2_records[idx - 1].get("record_hash"):
                    chain_ok = False
            join_prev = rec.get("prev_hash") if rec.get("prev_hash") else ""
            expected = hashlib.md5(
                (rec.get("file_hash") + join_prev + str(rec.get("timestamp"))).encode('utf-8')
            ).hexdigest()
            if expected != rec.get("record_hash"):
                chain_ok = False
        if not v2_records:
            chain_ok = False

        # 2.2 计算当前 md5
        try:
            with open('physical_state.jsonl', 'rb') as f:
                current_physical_hash = hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            print(json.dumps({"error": "physical_state.jsonl not found"}))
            sys.exit(0)

        try:
            with open('ai_hospital_rules.json', 'rb') as f:
                current_rules_hash = hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            print(json.dumps({"error": "ai_hospital_rules.json not found"}))
            sys.exit(0)

        # 2.3 生成监测事件
        def find_expected(file_name):
            for rec in reversed(records):
                if rec.get("file") == file_name:
                    return rec.get("file_hash")
            return None

        physical_expected = find_expected("physical_state.jsonl")
        physical_status = "no_reference" if physical_expected is None else (
            "ok" if current_physical_hash == physical_expected else "mismatch"
        )

        rules_expected = find_expected("ai_hospital_rules.json")
        rules_status = "no_reference" if rules_expected is None else (
            "ok" if current_rules_hash == rules_expected else "mismatch"
        )

        events = [
            {
                "event_id": "evt_001",
                "event_type": "file_hash_check",
                "file": "physical_state.jsonl",
                "current_hash": current_physical_hash,
                "expected_hash": physical_expected,
                "status": physical_status,
            },
            {
                "event_id": "evt_002",
                "event_type": "file_hash_check",
                "file": "ai_hospital_rules.json",
                "current_hash": current_rules_hash,
                "expected_hash": rules_expected,
                "status": rules_status,
            },
            {
                "event_id": "evt_003",
                "event_type": "chain_integrity_check",
                "file": "hash_chain_v2.log",
                "status": "ok" if chain_ok else "broken",
            },
        ]

        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "events": events,
        }

        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
