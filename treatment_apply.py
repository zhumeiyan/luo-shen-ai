#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 治疗执行与恢复模块 treatment_apply.py"""
import hashlib
import json
import time


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return [json.loads(line) for line in lines]


def read_last_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


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


def expected_hash(records, file_name):
    for rec in reversed(records):
        if rec.get("file") == file_name:
            return rec.get("file_hash")
    return None


def main():
    try:
        # AI 医院网关检查
        try:
            from hospital_gateway import check as hospital_check
            gate = hospital_check("treatment", "event_log.jsonl")
            if not gate.get("allow"):
                print(json.dumps({"blocked_by": "hospital_gateway", "reason": gate.get("reason")}))
                return
        except Exception:
            pass

        # 2.1 创建回滚点（二进制复制，已存在则覆盖）
        with open('event_log.jsonl', 'rb') as src, open('event_log.backup.jsonl', 'wb') as dst:
            dst.write(src.read())
        with open('hash_chain_v2.log', 'rb') as src, open('hash_chain_v2.backup.log', 'wb') as dst:
            dst.write(src.read())

        # 2.2 对 event_log.jsonl 执行哈希补录
        with open('event_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records = load_chain_records('hash_chain_v2.log')
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
            "file": "event_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.3 重新验证链完整性
        records = load_chain_records('hash_chain_v2.log')
        chain_status = "ok" if verify_chain(records) else "broken"

        # 2.4 重新运行诊断逻辑
        events = []
        with open('event_log.jsonl', 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        for line in lines[-3:]:
            events.append(json.loads(line))

        diagnosis_after = []
        for evt in events:
            if evt.get("event_type") == "chain_integrity_check":
                diagnosis_after.append({
                    "event_id": evt.get("event_id"),
                    "event_type": evt.get("event_type"),
                    "file": evt.get("file"),
                    "diagnosis": "confirmed_ok" if chain_status == "ok" else "confirmed_issue",
                })
            else:
                target = evt.get("file")
                expected = expected_hash(records, target)
                current = md5_of(target)
                diagnosis = "confirmed_ok" if expected is not None and current == expected else "confirmed_issue"
                diagnosis_after.append({
                    "event_id": evt.get("event_id"),
                    "event_type": evt.get("event_type"),
                    "file": target,
                    "diagnosis": diagnosis,
                })

        issue_count = sum(1 for d in diagnosis_after if d.get("diagnosis") == "confirmed_issue")

        # 2.5 重新计算健康评分（按 health_score_v2.py 逻辑，仅输出不写入）
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
        hash_ok_count = 0
        for name in files_14:
            expected = expected_hash(records, name)
            if expected is None:
                continue
            try:
                current = md5_of(name)
            except FileNotFoundError:
                continue
            if current == expected:
                hash_ok_count += 1
        hash_consistency = 20.0 * (hash_ok_count / 14.0)

        chain_integrity = 20.0 if chain_status == "ok" else 0.0

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

        safety_last = read_last_jsonl('safety_status.jsonl')
        safety_status = "unknown"
        if safety_last is not None:
            safety_status = safety_last.get("safety_status", "unknown")
        if safety_status == "normal":
            safety_score = 20.0
        elif safety_status == "isolated":
            safety_score = 5.0
        else:
            safety_score = 10.0

        total_score = round(
            file_integrity + hash_consistency + chain_integrity + issue_penalty + safety_score,
            2
        )

        if total_score >= 95:
            grade = "healthy"
        elif total_score >= 85:
            grade = "good"
        elif total_score >= 70:
            grade = "warning"
        else:
            grade = "critical"

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
        }

        # 2.6 生成治疗执行记录
        treatment_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "treatment_id": "treatment_apply_001",
            "actions": ["创建回滚点", "对 event_log.jsonl 执行哈希补录", "重新验证链完整性", "重新诊断", "重新评分"],
            "chain_status": chain_status,
            "diagnosis_after": diagnosis_after,
            "score_after": total_score,
            "grade_after": grade,
        }

        with open('treatment_apply_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(treatment_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        print(json.dumps(chain_record, ensure_ascii=False))
        print()
        print(chain_status)
        print()
        print(json.dumps({"schema_version": 1, "timestamp": time.time(), "diagnosis_results": diagnosis_after}, indent=2, ensure_ascii=False))
        print()
        print(json.dumps(score_record, indent=2, ensure_ascii=False))
        print()
        print(json.dumps(treatment_record, indent=2, ensure_ascii=False))
    except FileNotFoundError as e:
        name = str(e.filename) if hasattr(e, 'filename') else str(e)
        if 'event_log.jsonl' in name:
            print(json.dumps({"error": "event_log.jsonl not found"}))
        elif 'hash_chain_v2.log' in name:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
        else:
            print(json.dumps({"error": str(e)}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
