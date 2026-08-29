#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 诊断结果持久化模块 diagnosis_logger.py"""
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


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    try:
        try:
            with open('event_log.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "event_log.jsonl not found"}))
            return

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            chain_records = [json.loads(ln) for ln in chain_lines]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        events = [json.loads(ln) for ln in lines]
        last_events = events[-3:] if len(events) >= 3 else events

        diagnosis_results = []
        for ev in last_events:
            etype = ev.get("event_type")
            fname = ev.get("file")
            if etype == "file_hash_check":
                try:
                    current = md5_of(fname)
                    diagnosis = "confirmed_ok" if current == ev.get("current_hash") else "confirmed_issue"
                except FileNotFoundError:
                    diagnosis = "confirmed_issue"
            elif etype == "chain_integrity_check":
                diagnosis = "confirmed_ok" if verify_chain(chain_records) else "confirmed_issue"
            else:
                diagnosis = "unknown_event_type"
            diagnosis_results.append({
                "event_id": ev.get("event_id"),
                "event_type": etype,
                "file": fname,
                "diagnosis": diagnosis,
            })

        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "diagnosis_results": diagnosis_results,
        }

        with open('diagnosis_results.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')

        with open('diagnosis_results.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        prev_hash = None
        if chain_records:
            prev_hash = chain_records[-1].get("record_hash")

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "diagnosis_results.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(result, indent=2))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
