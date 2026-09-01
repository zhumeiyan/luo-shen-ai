#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 完整性监测扩展模块 integrity_monitor_v2.py
【安全修复】解析/校验失败以非零退出码结束（fail-closed）。"""
import hashlib
import json
import sys
import time


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    records = []
    for line_no, line in enumerate(lines, start=1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise RuntimeError("%s 第 %d 行损坏：%s" % (chain_file, line_no, e))
    return records


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
        # 2.1 读取 hash_chain_v2.log 并验证链连续性
        try:
            records = load_chain_records('hash_chain_v2.log')
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        chain_ok = verify_chain(records)

        # 2.2 读取三个文件并计算当前 md5
        file_names = ['physical_state.jsonl', 'ai_hospital_rules.json', 'event_log.jsonl']
        current_hashes = {}
        for name in file_names:
            try:
                with open(name, 'rb') as f:
                    current_hashes[name] = hashlib.md5(f.read()).hexdigest()
            except FileNotFoundError:
                print(json.dumps({"error": name + " not found"}))
                return

        # 2.3 生成四个监测事件
        def find_expected(file_name):
            for rec in reversed(records):
                if rec.get("file") == file_name:
                    return rec.get("file_hash")
            return None

        def hash_status(name):
            expected = find_expected(name)
            if expected is None:
                return expected, "no_reference"
            if current_hashes[name] == expected:
                return expected, "ok"
            return expected, "mismatch"

        exp_phys, status_phys = hash_status('physical_state.jsonl')
        exp_rules, status_rules = hash_status('ai_hospital_rules.json')
        exp_evt, status_evt = hash_status('event_log.jsonl')

        events = [
            {
                "event_id": "evt_004",
                "event_type": "file_hash_check",
                "file": "physical_state.jsonl",
                "current_hash": current_hashes['physical_state.jsonl'],
                "expected_hash": exp_phys,
                "status": status_phys,
            },
            {
                "event_id": "evt_005",
                "event_type": "file_hash_check",
                "file": "ai_hospital_rules.json",
                "current_hash": current_hashes['ai_hospital_rules.json'],
                "expected_hash": exp_rules,
                "status": status_rules,
            },
            {
                "event_id": "evt_006",
                "event_type": "file_hash_check",
                "file": "event_log.jsonl",
                "current_hash": current_hashes['event_log.jsonl'],
                "expected_hash": exp_evt,
                "status": status_evt,
            },
            {
                "event_id": "evt_007",
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

        # 2.4 将每个事件单独追加写入 event_log.jsonl
        for event in events:
            with open('event_log.jsonl', 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')

        # 2.5 为 integrity_monitor_v2.py 计算 md5 并追加哈希链
        with open('integrity_monitor_v2.py', 'rb') as f:
            script_hash = hashlib.md5(f.read()).hexdigest()
        last_record = records[-1] if records else None
        prev_hash = last_record.get("record_hash") if last_record else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (script_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "integrity_monitor_v2.py",
            "file_hash": script_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        print(json.dumps(result, indent=2))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
        # fail-closed：链断或任一受监测文件哈希不一致时以非零退出码告警
        mismatch = not chain_ok or status_phys == "mismatch" \
            or status_rules == "mismatch" or status_evt == "mismatch"
        sys.exit(1 if mismatch else 0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
