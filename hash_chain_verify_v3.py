#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 哈希链验证模块 hash_chain_verify_v3.py
【安全修复】fail-closed：任何校验失败/日志缺失/解析错误都输出 broken 并以非零退出码结束。"""
import hashlib
import json
import sys
import time


def main():
    try:
        with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        # fail-closed：日志缺失视为校验失败，而非成功
        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chain_length": 0,
            "chain_status": "broken",
            "error": "hash_chain_v2.log not found",
            "issues": [{"issue_type": "log_missing", "detail": "hash_chain_v2.log not found"}],
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)
    except Exception as e:
        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chain_length": 0,
            "chain_status": "broken",
            "error": str(e),
            "issues": [{"issue_type": "log_read_error", "detail": str(e)}],
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    records = []
    issues = []
    for idx, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            # fail-closed：发现坏行立即视为 broken
            issues.append({
                "line_number": idx,
                "issue_type": "parse_error",
                "detail": "bad json line: %s" % e,
            })

    if issues:
        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chain_length": len(records),
            "chain_status": "broken",
            "issues": issues,
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    try:
        with open('physical_state.jsonl', 'rb') as f:
            current_file_hash = hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        print(json.dumps({"chain_status": "broken", "error": "physical_state.jsonl not found"}))
        sys.exit(1)

    for idx, rec in enumerate(records):
        line_number = idx + 1
        prev_hash = rec.get("prev_hash")
        file_hash = rec.get("file_hash")
        timestamp = rec.get("timestamp")
        record_hash = rec.get("record_hash")

        if file_hash is None or record_hash is None:
            issues.append({
                "line_number": line_number,
                "issue_type": "missing_field",
                "detail": "record missing file_hash/record_hash",
            })
            continue

        if idx == 0:
            if prev_hash is not None:
                issues.append({
                    "line_number": line_number,
                    "issue_type": "invalid_genesis",
                    "detail": "first record prev_hash is not null",
                })
        else:
            if prev_hash != records[idx - 1].get("record_hash"):
                issues.append({
                    "line_number": line_number,
                    "issue_type": "chain_broken",
                    "detail": "prev_hash does not match previous record_hash",
                })

        join_prev = prev_hash if prev_hash else ""
        expected = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        if expected != record_hash:
            issues.append({
                "line_number": line_number,
                "issue_type": "record_hash_mismatch",
                "detail": "record_hash does not match recomputed value",
            })

    # 只与链上最近一条 physical_state.jsonl 的记录比对，
    # 不能用“链上最后一条记录”（通常被其它模块的报告文件占用）来比较。
    phys_ref = None
    for rec in reversed(records):
        if rec.get("file") == "physical_state.jsonl":
            phys_ref = rec
            break
    if phys_ref is not None:
        if phys_ref.get("file_hash") != current_file_hash:
            issues.append({
                "line_number": records.index(phys_ref) + 1,
                "issue_type": "file_tampered",
                "detail": "physical_state.jsonl hash does not match its latest chain record",
            })
    else:
        issues.append({
            "issue_type": "no_reference",
            "detail": "hash_chain_v2.log 中缺少 physical_state.jsonl 的链记录",
        })

    result = {
        "schema_version": 1,
        "timestamp": time.time(),
        "chain_length": len(records),
        "chain_status": "ok" if not issues else "broken",
        "current_file_hash": current_file_hash,
        "issues": issues,
    }

    print(json.dumps(result, indent=2))
    # fail-closed：有任一问题都返回非零退出码
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()