#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 治疗决策基础模块 treatment_decision.py"""
import hashlib
import json
import time


def main():
    try:
        try:
            with open('diagnosis_results.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "diagnosis_results.jsonl not found"}))
            return

        if not lines:
            issue_count = 0
        else:
            last_record = json.loads(lines[-1])
            diag_results = last_record.get("diagnosis_results", [])
            issue_count = sum(
                1 for d in diag_results if d.get("diagnosis") == "confirmed_issue"
            )

        decision = "no_treatment_needed" if issue_count == 0 else "observe_only"
        reason = (
            "no issues detected"
            if issue_count == 0
            else "issues exist but not yet classified as critical"
        )

        decision_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "source_diagnosis_file": "diagnosis_results.jsonl",
            "issue_count": issue_count,
            "decision": decision,
            "reason": reason,
        }

        with open('treatment_decisions.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(decision_record, ensure_ascii=False) + '\n')

        with open('treatment_decisions.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        prev_hash = None
        if chain_lines:
            last_record = json.loads(chain_lines[-1])
            prev_hash = last_record.get("record_hash")

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "treatment_decisions.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(decision_record, indent=2))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
