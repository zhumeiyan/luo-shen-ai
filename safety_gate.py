#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 安全状态检查模块 safety_gate.py"""
import hashlib
import json
import time


def verify_chain(records):
    v2_records = [r for r in records if r.get("schema_version") == 2]
    if not v2_records:
        return False
    for idx, rec in enumerate(v2_records):
        if idx == 0:
            if rec.get("prev_hash") is not None:
                return False
        else:
            if rec.get("prev_hash") != v2_records[idx - 1].get("record_hash"):
                return False
        join_prev = rec.get("prev_hash") if rec.get("prev_hash") else ""
        expected = hashlib.md5(
            (rec.get("file_hash") + join_prev + str(rec.get("timestamp"))).encode('utf-8')
        ).hexdigest()
        if expected != rec.get("record_hash"):
            return False
    return True


def main():
    try:
        # 2.1 读取 treatment_decisions.jsonl 最后一条记录
        issue_count = 0
        try:
            with open('treatment_decisions.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if lines:
                last_record = json.loads(lines[-1])
                issue_count = last_record.get("issue_count", 0)
        except FileNotFoundError:
            issue_count = 0

        # 2.2 读取 hash_chain_v2.log 并验证链连续性
        chain_ok = False
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            records = [json.loads(ln) for ln in chain_lines]
            chain_ok = verify_chain(records)
        except FileNotFoundError:
            chain_ok = False

        # 2.3 生成安全状态
        if issue_count > 3 or not chain_ok:
            safety_status = "isolated"
        else:
            safety_status = "normal"

        action = "stop_auto_operations" if safety_status == "isolated" else "continue"

        status_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "safety_status": safety_status,
            "issue_count": issue_count,
            "chain_ok": chain_ok,
            "action": action,
        }

        # 2.4 追加写入 safety_status.jsonl
        with open('safety_status.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(status_record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        with open('safety_status.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        prev_hash = None
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if chain_lines:
                prev_hash = json.loads(chain_lines[-1]).get("record_hash")
        except FileNotFoundError:
            prev_hash = None

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "safety_status.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(status_record, indent=2))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
