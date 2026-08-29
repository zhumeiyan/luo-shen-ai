#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 内部闭环总控模块（自动指纹同步版） internal_loop_v2.py"""
import hashlib
import json
import sys
import time
import subprocess
import os

PROTECTED_FILES = [
    "physical_state.jsonl",
    "ai_hospital_rules.json",
    "event_log.jsonl",
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
    "external_diagnosis_report.json",
]

INTERNAL_MODULES = [
    ("integrity_monitor", "integrity_monitor_v2.py"),
    ("diagnosis_logger", "diagnosis_logger.py"),
    ("health_score", "health_score_v2.py"),
    ("safety_gate", "safety_gate.py"),
]


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def load_chain():
    records = []
    if not os.path.exists('hash_chain_v2.log'):
        return records
    with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise RuntimeError("hash_chain_v2.log 第 %d 行损坏：%s" % (line_no, e))
    return records


def last_expected(records, fname):
    """取链上该文件最后一条记录的 file_hash，无则 None"""
    expected = None
    for rec in records:
        if rec.get("file") == fname:
            expected = rec.get("file_hash")
    return expected


def append_chain(records, fname, file_hash):
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
        "file": fname,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')
    records.append(chain_record)
    return chain_record


def run_module(name, script):
    try:
        proc = subprocess.run(
            ["python", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0:
            return "ok", proc.stdout
        return "failed", proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return "timeout", ""
    except Exception:
        return "failed", ""


def verify_chain(records):
    v2_records = [r for r in records if r.get("schema_version") == 2]
    prev_record_hash = None
    for i, rec in enumerate(v2_records):
        if i == 0:
            if rec.get("prev_hash") is not None:
                return "broken"
        else:
            if rec.get("prev_hash") != prev_record_hash:
                return "broken"
        join_prev = rec.get("prev_hash") if rec.get("prev_hash") else ""
        recalc = hashlib.md5(
            (rec.get("file_hash", "") + join_prev + str(rec.get("timestamp"))).encode('utf-8')
        ).hexdigest()
        if recalc != rec.get("record_hash"):
            return "broken"
        prev_record_hash = rec.get("record_hash")
    return "ok"


def read_last_jsonl(path):
    if not os.path.exists(path):
        return None
    last = None
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    return last


def main():
    try:
        # 2.1 依次运行四个内部模块
        mod_results = {}
        mod_outputs = {}
        for name, script in INTERNAL_MODULES:
            status, out = run_module(name, script)
            mod_results[name] = status
            mod_outputs[name] = out

        # 2.2 读取哈希链
        records = load_chain()

        # 2.3 对受保护文件自动指纹同步补链
        # 【安全修复】仅对从未上链的文件建立基线；
        # 已上链但哈希不一致的文件视为篡改，绝不自动重新上链赦免。
        sync_records = []
        tampered_files = []
        for fname in PROTECTED_FILES:
            if not os.path.exists(fname):
                continue
            current_hash = md5_of(fname)
            expected = last_expected(records, fname)
            if expected is None:
                # 首次出现：建立基线
                chain_record = append_chain(records, fname, current_hash)
                sync_records.append(chain_record)
            elif current_hash != expected:
                # 与链上基线不一致：标记篡改，不自动赦免
                tampered_files.append(fname)

        # 2.4 读取内部病历本文件最新状态
        diag_last = read_last_jsonl('diagnosis_results.jsonl')
        if diag_last is None:
            diagnosis_last = "unknown"
        else:
            try:
                arr = diag_last.get("diagnosis_results", [])
                diagnosis_last = arr[-1].get("diagnosis", "unknown") if arr else "unknown"
            except Exception:
                diagnosis_last = "unknown"

        score_last = read_last_jsonl('health_score.jsonl')
        if score_last is None:
            health_score_val = None
            grade = "unknown"
        else:
            try:
                health_score_val = score_last.get("total_score")
            except Exception:
                health_score_val = None
            try:
                grade = score_last.get("grade", "unknown")
            except Exception:
                grade = "unknown"

        safety_last = read_last_jsonl('safety_status.jsonl')
        if safety_last is None:
            safety_status = "unknown"
        else:
            try:
                safety_status = safety_last.get("safety_status", "unknown")
            except Exception:
                safety_status = "unknown"

        # 2.5 生成内部闭环报告（v2）
        if tampered_files:
            chain_state = "tampered"
        elif verify_chain(records):
            chain_state = "ok"
        else:
            chain_state = "broken"
        report = {
            "schema_version": 2,
            "timestamp": time.time(),
            "loop_id": "internal_loop_v2_001",
            "modules": mod_results,
            "latest_status": {
                "diagnosis_last": diagnosis_last,
                "health_score": health_score_val,
                "grade": grade,
                "safety_status": safety_status,
            },
            "chain_status": chain_state,
            "tampered_files": tampered_files,
            "sync_count": len(sync_records),
            "synced_files": [r.get("file") for r in sync_records],
        }

        # 2.6 追加写入 internal_loop_report_v2.jsonl
        with open('internal_loop_report_v2.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(report, ensure_ascii=False) + '\n')

        # 2.7 为报告文件计算 md5 并追加哈希链
        with open('internal_loop_report_v2.jsonl', 'rb') as f:
            report_file_hash = hashlib.md5(f.read()).hexdigest()
        report_chain = append_chain(records, 'internal_loop_report_v2.jsonl', report_file_hash)

        # 2.8 标准输出
        print(json.dumps(report, ensure_ascii=False))
        print()
        print(json.dumps(report_chain, ensure_ascii=False))
        # fail-closed：检测到篡改/断链/模块失败时以非零退出码告警
        if tampered_files or chain_state != "ok" or any(
            s != "ok" for s in mod_results.values()
        ):
            sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
