#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 事件验证与诊断模块 diagnosis_basic.py"""
import hashlib
import json
import time


def verify_chain(chain_file):
    """重新验证链连续性，返回 True 表示连续。"""
    try:
        with open(chain_file, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return False
    if not lines:
        return False
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except Exception:
            return False
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
        # 2.1 读取 event_log.jsonl
        try:
            with open('event_log.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "event_log.jsonl not found"}))
            return

        events = []
        for line in lines:
            events.append(json.loads(line))
        last_events = events[-3:] if len(events) >= 3 else events

        # 2.2 对每条事件重新验证
        diagnosis_results = []
        for ev in last_events:
            event_id = ev.get("event_id")
            event_type = ev.get("event_type")
            file_name = ev.get("file")

            if event_type == "file_hash_check":
                try:
                    with open(file_name, 'rb') as f:
                        current_md5 = hashlib.md5(f.read()).hexdigest()
                except FileNotFoundError:
                    diagnosis = "confirmed_issue"
                else:
                    if current_md5 == ev.get("current_hash"):
                        diagnosis = "confirmed_ok"
                    else:
                        diagnosis = "confirmed_issue"
            elif event_type == "chain_integrity_check":
                if verify_chain("hash_chain_v2.log"):
                    diagnosis = "confirmed_ok"
                else:
                    diagnosis = "confirmed_issue"
            else:
                diagnosis = "unknown_event_type"

            diagnosis_results.append({
                "event_id": event_id,
                "event_type": event_type,
                "file": file_name,
                "diagnosis": diagnosis,
            })

        # 2.3/2.4 生成并打印诊断结果 JSON
        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "diagnosis_results": diagnosis_results,
        }
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
