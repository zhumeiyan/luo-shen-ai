#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 健康评分修正模块 health_score_v2.py"""
import hashlib
import json
import time


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return [json.loads(line) for line in lines]


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


def read_last_jsonl(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except FileNotFoundError:
        return None


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

        # 2.1 读取当前系统状态
        chain_ok = verify_chain(records)

        diag_last = read_last_jsonl('diagnosis_results.jsonl')
        issue_count = 0
        if diag_last is not None:
            diag_list = diag_last.get("diagnosis_results", [])
            issue_count = sum(
                1 for item in diag_list
                if item.get("diagnosis") == "confirmed_issue"
            )

        safety_last = read_last_jsonl('safety_status.jsonl')
        safety_status = "unknown"
        if safety_last is not None:
            safety_status = safety_last.get("safety_status", "unknown")

        # 2.2 检查文件完整性
        files_16 = [
            'physical_state.jsonl',
            'ai_hospital_rules.json',
            'event_log.jsonl',
            'hash_chain_v2.log',
            'precheck_report.json',
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
        existing_count = 0
        for name in files_16:
            try:
                with open(name, 'rb') as f:
                    f.read(1)
                existing_count += 1
            except FileNotFoundError:
                pass
        file_integrity = 20.0 * (existing_count / 16.0)

        # 2.3 检查哈希一致性
        files_14 = [
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

        def expected_hash(file_name):
            for rec in reversed(records):
                if rec.get("file") == file_name:
                    return rec.get("file_hash")
            return None

        hash_ok_count = 0
        for name in files_14:
            expected = expected_hash(name)
            if expected is None:
                continue
            try:
                current = md5_of(name)
            except FileNotFoundError:
                continue
            if current == expected:
                hash_ok_count += 1
        hash_consistency = 20.0 * (hash_ok_count / 14.0)

        # 2.4 链完整性得分
        chain_integrity = 20.0 if chain_ok else 0.0

        # 2.5 问题得分
        if issue_count == 0:
            issue_penalty = 20.0
        elif issue_count == 1:
            issue_penalty = 15.0
        elif issue_count == 2:
            issue_penalty = 10.0
        elif issue_count in (3, 4):
            issue_penalty = 5.0
        else:
            issue_penalty = 0.0

        # 2.6 安全状态得分
        if safety_status == "normal":
            safety_score = 20.0
        elif safety_status == "isolated":
            safety_score = 5.0
        else:
            safety_score = 10.0

        # 2.7 计算总分
        total_score = round(
            file_integrity + hash_consistency + chain_integrity + issue_penalty + safety_score,
            2
        )

        # 2.8 等级与安全动作
        if total_score >= 95:
            grade = "healthy"
        elif total_score >= 85:
            grade = "good"
        elif total_score >= 70:
            grade = "warning"
        else:
            grade = "critical"

        if grade == "healthy":
            action = "normal_auto"
        elif grade == "good":
            action = "auto_with_attention"
        elif grade == "warning":
            action = "human_review"
        else:
            action = "stop_auto_operations"

        # 2.9 生成健康评分记录
        score_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "scores": {
                "file_integrity": file_integrity,
                "hash_consistency": hash_consistency,
                "chain_integrity": chain_integrity,
                "issue_penalty": issue_penalty,
                "safety_status": safety_score,
            },
            "total_score": total_score,
            "grade": grade,
            "action": action,
        }

        # 2.10 追加写入 health_score.jsonl
        with open('health_score.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(score_record, ensure_ascii=False) + '\n')

        # 2.11 计算 md5 并追加哈希链
        with open('health_score.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        prev_hash = None
        if records:
            prev_hash = records[-1].get("record_hash")

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "health_score.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.12 标准输出
        print(json.dumps(score_record, indent=2))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
