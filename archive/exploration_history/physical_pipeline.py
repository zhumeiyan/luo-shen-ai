#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 物理状态哈希链自动流水线 physical_pipeline.py"""
import hashlib
import json
import sys
import time


def main():
    try:
        import psutil
    except ImportError:
        print(json.dumps({"error": "psutil not installed"}))
        sys.exit(0)

    try:
        proc = psutil.Process()

        static_limits = {
            "cpu_logical_cores": psutil.cpu_count(logical=True),
            "cpu_physical_cores": psutil.cpu_count(logical=False),
            "memory_total_bytes": psutil.virtual_memory().total,
            "disk_total_bytes": psutil.disk_usage('/').total,
        }

        dynamic_usage = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "process_cpu_percent": proc.cpu_percent(interval=0.1),
            "memory_used_bytes": psutil.virtual_memory().used,
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "process_runtime_seconds": time.time() - proc.create_time(),
        }

        memory_total = static_limits["memory_total_bytes"]
        disk_total = static_limits["disk_total_bytes"]
        memory_remaining_ratio = 1 - (dynamic_usage["memory_used_bytes"] / memory_total)
        cpu_remaining_ratio = 1 - (dynamic_usage["cpu_percent"] / 100)
        disk_remaining_ratio = 1 - (dynamic_usage["disk_percent"] / 100)
        danger_level = 1 - min(memory_remaining_ratio, cpu_remaining_ratio, disk_remaining_ratio)

        if danger_level > 0.8:
            status = "critical"
        elif danger_level > 0.6:
            status = "warning"
        else:
            status = "normal"

        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "static_limits": static_limits,
            "dynamic_usage": dynamic_usage,
            "computed": {
                "memory_remaining_ratio": memory_remaining_ratio,
                "cpu_remaining_ratio": cpu_remaining_ratio,
                "disk_remaining_ratio": disk_remaining_ratio,
                "danger_level": danger_level,
                "status": status,
            }
        }

        # 2.2 写入物理状态日志
        with open('physical_state.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')

        # 2.3 更新哈希链
        with open('physical_state.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        prev_hash = None
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                lines = f.readlines()
            records = []
            for line in lines:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
            if records:
                prev_hash = records[-1].get("record_hash")
        except FileNotFoundError:
            pass

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "physical_state.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.4 验证整条链
        with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
            chain_lines = f.readlines()
        chain_records = []
        for line in chain_lines:
            line = line.strip()
            if line:
                chain_records.append(json.loads(line))

        with open('physical_state.jsonl', 'rb') as f:
            current_file_hash = hashlib.md5(f.read()).hexdigest()

        issues = []
        for idx, rec in enumerate(chain_records):
            line_number = idx + 1
            rec_prev = rec.get("prev_hash")
            rec_file = rec.get("file_hash")
            rec_ts = rec.get("timestamp")
            rec_rh = rec.get("record_hash")

            if idx == 0:
                if rec_prev is not None:
                    issues.append({
                        "line_number": line_number,
                        "issue_type": "invalid_genesis",
                        "detail": "first record prev_hash is not null",
                    })
            else:
                if rec_prev != chain_records[idx - 1].get("record_hash"):
                    issues.append({
                        "line_number": line_number,
                        "issue_type": "chain_broken",
                        "detail": "prev_hash does not match previous record_hash",
                    })

            join = rec_prev if rec_prev else ""
            expected = hashlib.md5(
                (rec_file + join + str(rec_ts)).encode('utf-8')
            ).hexdigest()
            if expected != rec_rh:
                issues.append({
                    "line_number": line_number,
                    "issue_type": "record_hash_mismatch",
                    "detail": "record_hash does not match recomputed value",
                })

        if chain_records:
            if chain_records[-1].get("file_hash") != current_file_hash:
                issues.append({
                    "line_number": len(chain_records),
                    "issue_type": "file_tampered",
                    "detail": "last file_hash does not match current physical_state.jsonl hash",
                })

        verify_result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chain_length": len(chain_records),
            "chain_status": "ok" if not issues else "broken",
            "current_file_hash": current_file_hash,
            "issues": issues,
        }

        # 2.5 标准输出
        print(json.dumps(result, indent=2))
        print()
        print(json.dumps(chain_record, indent=2))
        print()
        print(json.dumps(verify_result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
