#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 全系统健康检查模块 total_health_check.py"""
import hashlib
import json
import time


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    records = []
    for line in lines:
        records.append(json.loads(line))
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


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    try:
        try:
            records = load_chain_records('hash_chain_v2.log')
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        chain_status = "ok" if verify_chain(records) else "broken"

        tracked_files = [
            'physical_state.jsonl',
            'ai_hospital_rules.json',
            'event_log.jsonl',
            'hospital_rules/principles.json',
            'hospital_rules/terms.json',
            'hospital_rules/validation_flow.json',
            'hospital_rules/architect_precheck.json',
            'hospital_rules/executor_delivery_checklist.json',
            'hospital_rules/audit_rule.json',
            'hospital_rules/version_control.json',
            'diagnosis_results.jsonl',
            'treatment_decisions.jsonl',
            'followup_plan.jsonl',
            'safety_status.jsonl',
        ]

        files = [
            {"file": "physical_state.jsonl", "hash_status": "not_applicable"},
            {"file": "ai_hospital_rules.json", "hash_status": "not_applicable"},
            {"file": "event_log.jsonl", "hash_status": "not_applicable"},
            {"file": "hash_chain_v2.log", "hash_status": "not_applicable"},
            {"file": "precheck_report.json", "hash_status": "not_applicable"},
            {"file": "hospital_rules/principles.json", "hash_status": "not_applicable"},
            {"file": "hospital_rules/terms.json", "hash_status": "not_applicable"},
            {"file": "hospital_rules/validation_flow.json", "hash_status": "not_applicable"},
            {"file": "hospital_rules/architect_precheck.json", "hash_status": "not_applicable"},
            {"file": "hospital_rules/executor_delivery_checklist.json", "hash_status": "not_applicable"},
            {"file": "hospital_rules/audit_rule.json", "hash_status": "not_applicable"},
            {"file": "hospital_rules/version_control.json", "hash_status": "not_applicable"},
            {"file": "diagnosis_results.jsonl", "hash_status": "not_applicable"},
            {"file": "treatment_decisions.jsonl", "hash_status": "not_applicable"},
            {"file": "followup_plan.jsonl", "hash_status": "not_applicable"},
            {"file": "safety_status.jsonl", "hash_status": "not_applicable"},
        ]

        def expected_hash(file_name):
            for rec in reversed(records):
                if rec.get("file") == file_name:
                    return rec.get("file_hash")
            return None

        for item in files:
            name = item["file"]
            exists = False
            try:
                with open(name, 'rb') as f:
                    f.read(1)
                exists = True
            except FileNotFoundError:
                exists = False
            item["exists"] = exists

            if name in tracked_files:
                if not exists:
                    item["hash_status"] = "no_reference"
                    continue
                expected = expected_hash(name)
                if expected is None:
                    item["hash_status"] = "no_reference"
                else:
                    current = md5_of(name)
                    item["hash_status"] = "ok" if current == expected else "mismatch"

        report = {
            "schema_version": 1,
            "timestamp": time.time(),
            "files": files,
            "chain_status": chain_status,
        }

        print(json.dumps(report, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
