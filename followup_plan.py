#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 复查计划生成模块 followup_plan.py"""
import hashlib
import json
import time


def main():
    try:
        try:
            with open('treatment_decisions.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "treatment_decisions.jsonl not found"}))
            return

        if not lines:
            print(json.dumps({"error": "treatment_decisions.jsonl empty"}))
            return

        last_record = json.loads(lines[-1])
        decision = last_record.get("decision")
        issue_count = last_record.get("issue_count", 0)

        if decision == "no_treatment_needed":
            empty_plan = {
                "schema_version": 1,
                "timestamp": time.time(),
                "plan_generated": False,
                "reason": "no_treatment_needed",
            }
            print(json.dumps(empty_plan, indent=2))
            return

        decision = "observe_only" if decision != "observe_only" else decision

        timestamp = time.time()
        plan_record = {
            "schema_version": 1,
            "timestamp": timestamp,
            "source_decision_file": "treatment_decisions.jsonl",
            "issue_count": issue_count,
            "next_check_time": timestamp + 86400,
            "plan_generated": True,
        }

        with open('followup_plan.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(plan_record, ensure_ascii=False) + '\n')

        with open('followup_plan.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        prev_hash = None
        if chain_lines:
            prev_hash = json.loads(chain_lines[-1]).get("record_hash")

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "followup_plan.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(plan_record, indent=2))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
