#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 健康分数下降排查模块 health_drop_investigation.py（全程只读）"""
import hashlib
import json
import time
import os

DATA_FILES_16 = [
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
    "diagnosis_results.jsonl",
    "treatment_decisions.jsonl",
    "followup_plan.jsonl",
    "safety_status.jsonl",
]

MANAGED_FILES_14 = [
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
    "diagnosis_results.jsonl",
    "treatment_decisions.jsonl",
    "followup_plan.jsonl",
    "safety_status.jsonl",
]


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    try:
        # 2.1 读取 health_score.jsonl 最后一条记录
        try:
            last = None
            with open('health_score.jsonl', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = json.loads(line)
        except FileNotFoundError:
            print(json.dumps({"error": "health_score.jsonl not found"}))
            return

        scores = last.get("scores", {})
        score_detail = {
            "file_integrity": scores.get("file_integrity"),
            "hash_consistency": scores.get("hash_consistency"),
            "chain_integrity": scores.get("chain_integrity"),
            "issue_penalty": scores.get("issue_penalty"),
            "safety_status": scores.get("safety_status"),
            "total_score": last.get("total_score"),
            "grade": last.get("grade"),
        }

        # 2.2 检查16个数据文件是否存在
        data_files_exist = {}
        for fname in DATA_FILES_16:
            data_files_exist[fname] = os.path.exists(fname)

        # 2.3 检查14个受管文件哈希状态
        try:
            records = []
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        last_chain = {}
        for rec in records:
            if rec.get("schema_version") == 2:
                last_chain[rec.get("file")] = rec.get("file_hash")

        hash_status = {}
        for fname in MANAGED_FILES_14:
            if not os.path.exists(fname):
                hash_status[fname] = "missing"
            elif fname not in last_chain:
                hash_status[fname] = "no_reference"
            else:
                cur = md5_of(fname)
                if cur == last_chain[fname]:
                    hash_status[fname] = "ok"
                else:
                    hash_status[fname] = "mismatch"

        # 2.4 生成排查报告
        report = {
            "schema_version": 1,
            "timestamp": time.time(),
            "score_detail": score_detail,
            "data_files_exist": data_files_exist,
            "hash_status": hash_status,
        }

        # 2.5 标准输出
        print(json.dumps(report, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
