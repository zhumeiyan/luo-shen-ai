#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 全模块健康体检 full_health_check.py（全程只读）"""
import hashlib
import json
import time
import os

DATA_FILES = [
    "physical_state.jsonl",
    "ai_hospital_rules.json",
    "event_log.jsonl",
    "hash_chain_v2.log",
    "precheck_report.json",
    "hospital_rules/principles.json",
    "hospital_rules/terms.json",
    "hospital_rules/validation_flow.json",
    "hospital_rules/architect_precheck.json",
    "hospital_rules/executor_delivery_checklist.json",
    "hospital_rules/audit_rule.json",
    "hospital_rules/version_control.json",
    "hospital_rules/repair_credits.json",
    "hospital_rules/revisit_rules.json",
    "diagnosis_results.jsonl",
    "treatment_decisions.jsonl",
    "followup_plan.jsonl",
    "safety_status.jsonl",
    "health_score.jsonl",
    "treatment_plans.jsonl",
    "treatment_apply_log.jsonl",
    "repair_count_log.jsonl",
    "repair_events.jsonl",
    "repair_counter_log.jsonl",
]

SCRIPT_FILES = [
    "physical_sensor_step1.py",
    "physical_sensor_step2.py",
    "physical_sensor_step3.py",
    "physical_sensor_step4.py",
    "physical_sensor_step5.py",
    "minimal_stimulus_test.py",
    "hash_chain_verify.py",
    "hash_chain_v2.py",
    "hash_chain_verify_v2.py",
    "hash_chain_v2_init.py",
    "hash_chain_verify_v3.py",
    "physical_pipeline.py",
    "ai_hospital_rules.py",
    "rules_modular_init.py",
    "precheck_report.py",
    "event_log_chain_update.py",
    "integrity_monitor.py",
    "event_logger.py",
    "integrity_monitor_v2.py",
    "diagnosis_basic.py",
    "diagnosis_logger.py",
    "treatment_decision.py",
    "followup_plan.py",
    "safety_gate.py",
    "health_score.py",
    "health_score_v2.py",
    "treatment_executor.py",
    "treatment_integrative.py",
    "treatment_apply.py",
    "hospital_rules_extra_init.py",
    "repair_counter.py",
    "repair_event.py",
    "repair_counter_v2.py",
    "event_log_chain_update_v2.py",
    "total_health_check.py",
]

PROTECTED_FILES = [
    "physical_state.jsonl",
    "ai_hospital_rules.json",
    "event_log.jsonl",
    "hospital_rules/principles.json",
    "hospital_rules/terms.json",
    "hospital_rules/validation_flow.json",
    "hospital_rules/architect_precheck.json",
    "hospital_rules/executor_delivery_checklist.json",
    "hospital_rules/audit_rule.json",
    "hospital_rules/version_control.json",
    "hospital_rules/repair_credits.json",
    "hospital_rules/revisit_rules.json",
    "diagnosis_results.jsonl",
    "treatment_decisions.jsonl",
    "followup_plan.jsonl",
    "safety_status.jsonl",
    "health_score.jsonl",
    "treatment_plans.jsonl",
    "treatment_apply_log.jsonl",
    "repair_count_log.jsonl",
    "repair_events.jsonl",
    "repair_counter_log.jsonl",
]


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    try:
        # 2.3 读取哈希链
        if not os.path.exists('hash_chain_v2.log'):
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        records = []
        with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        # 2.3 链连续性验证（仅 schema_version 为 2 的记录）
        chain_status = "ok"
        v2_records = [r for r in records if r.get("schema_version") == 2]
        prev_record_hash = None
        for i, rec in enumerate(v2_records):
            if i == 0:
                if rec.get("prev_hash") is not None:
                    chain_status = "broken"
                    break
            else:
                if rec.get("prev_hash") != prev_record_hash:
                    chain_status = "broken"
                    break
            join_prev = rec.get("prev_hash") if rec.get("prev_hash") else ""
            recalc = hashlib.md5(
                (rec.get("file_hash", "") + join_prev + str(rec.get("timestamp"))).encode('utf-8')
            ).hexdigest()
            if recalc != rec.get("record_hash"):
                chain_status = "broken"
                break
            prev_record_hash = rec.get("record_hash")

        # 链上每个文件最后一条记录
        last_chain = {}
        for rec in v2_records:
            last_chain[rec.get("file")] = rec.get("file_hash")

        # 2.1 数据文件存在性 + 2.4 哈希状态
        data_files = []
        for fname in DATA_FILES:
            exists = os.path.exists(fname)
            if not exists:
                hash_status = "missing"
            elif fname not in last_chain:
                hash_status = "no_reference"
            else:
                cur = md5_of(fname)
                if cur == last_chain[fname]:
                    hash_status = "ok"
                else:
                    hash_status = "mismatch"
            data_files.append({"file": fname, "exists": exists, "hash_status": hash_status})

        # 2.2 脚本文件存在性
        script_files = []
        for fname in SCRIPT_FILES:
            script_files.append({"file": fname, "exists": os.path.exists(fname)})

        # 2.5 生成体检报告
        report = {
            "schema_version": 1,
            "timestamp": time.time(),
            "data_files": data_files,
            "script_files": script_files,
            "chain_status": chain_status,
        }

        # 2.6 标准输出
        print(json.dumps(report, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
