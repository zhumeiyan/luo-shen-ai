#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 内部闭环总控模块 internal_loop.py"""
import hashlib
import json
import time
import subprocess
import os


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


def verify_chain():
    records = []
    with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

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
        for name, script in [
            ("integrity_monitor", "integrity_monitor_v2.py"),
            ("diagnosis_logger", "diagnosis_logger.py"),
            ("health_score", "health_score_v2.py"),
            ("safety_gate", "safety_gate.py"),
        ]:
            status, out = run_module(name, script)
            mod_results[name] = status
            mod_outputs[name] = out

        # 2.2 读取内部病历本文件最新状态
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

        # 2.3 生成内部闭环报告
        report = {
            "schema_version": 1,
            "timestamp": time.time(),
            "loop_id": "internal_loop_001",
            "modules": {
                "integrity_monitor": mod_results["integrity_monitor"],
                "diagnosis_logger": mod_results["diagnosis_logger"],
                "health_score": mod_results["health_score"],
                "safety_gate": mod_results["safety_gate"],
            },
            "latest_status": {
                "diagnosis_last": diagnosis_last,
                "health_score": health_score_val,
                "grade": grade,
                "safety_status": safety_status,
            },
            "chain_status": verify_chain(),
        }

        # 2.4 追加写入 internal_loop_report.jsonl
        with open('internal_loop_report.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(report, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        with open('internal_loop_report.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records = []
        with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

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
            "file": "internal_loop_report.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        print(json.dumps(report, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
