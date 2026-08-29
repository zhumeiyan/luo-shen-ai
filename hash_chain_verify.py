#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 哈希链完整性验证模块 hash_chain_verify.py

验证 v2 链（hash_chain_v2.log）：
1) 每条记录自洽：record_hash == md5(file_hash + prev_hash + str(timestamp))
2) 链式：第 i 条 prev_hash == 第 i-1 条 record_hash（链首允许空）
任何一条不符 → fail-closed 报 chain_broken。
"""
import hashlib
import json
import os
import sys
import time

CHAIN_NAME = "hash_chain_v2.log"


def rec_hash(file_hash, prev_hash, ts):
    h = hashlib.md5()
    h.update(str(file_hash).encode("utf-8"))
    h.update((prev_hash if prev_hash else "").encode("utf-8"))  # 与 v2 公式一致：空则用空串
    h.update(str(ts).encode("utf-8"))
    return h.hexdigest()


def main():
    try:
        with open(CHAIN_NAME, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(json.dumps({"error": "%s not found" % CHAIN_NAME}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)

    records = []
    for line in lines:
        line = line.strip()
        if line:
            records.append(json.loads(line))

    issues = []
    prev = ""  # 链首之前为空，允许首条 prev_hash 为 None/空
    for i, r in enumerate(records):
        exp = rec_hash(r.get("file_hash"), r.get("prev_hash"), r.get("timestamp"))
        if r.get("record_hash") != exp:
            issues.append({
                "index": i,
                "issue": "record_hash 自洽校验失败",
                "file": r.get("file"),
            })
        if i > 0 and r.get("prev_hash") != prev:
            issues.append({
                "index": i,
                "issue": "prev_hash 与上一条 record_hash 不匹配（链断裂）",
                "file": r.get("file"),
            })
        prev = r.get("record_hash")

    result = {
        "schema_version": 2,
        "timestamp": time.time(),
        "chain": CHAIN_NAME,
        "record_count": len(records),
        "verify_result": "ok" if not issues else "chain_broken",
        "issues": issues,
        "tail_record": {
            "file": records[-1].get("file") if records else None,
            "record_hash": records[-1].get("record_hash") if records else None,
        } if records else None,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()