#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""哈希链完整性验证脚本——只读，不修改任何文件。"""

import json
import hashlib
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

CHAIN_FILE = "hash_chain_v2.log"

def verify_chain():
    print("=" * 70)
    print("哈希链完整性验证")
    print("=" * 70)

    if not os.path.exists(CHAIN_FILE):
        print(f"找不到 {CHAIN_FILE}")
        return

    with open(CHAIN_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    print(f"\n总条数: {len(lines)}")

    if not lines:
        print("链为空")
        return

    records = []
    # ================================================================
    # 1. 逐条解析，检查字段完整性
    # ================================================================
    print("\n[检查 1] 字段完整性")
    all_fields_ok = True
    for i, line in enumerate(lines, 1):
        try:
            r = json.loads(line)
            records.append(r)
            required = ["schema_version", "timestamp", "file", "file_hash", "prev_hash", "record_hash"]
            missing = [k for k in required if k not in r]
            if missing:
                print(f"  ✗ 第{i}条缺少字段: {missing}")
                all_fields_ok = False
        except json.JSONDecodeError as e:
            print(f"  ✗ 第{i}条 JSON 解析失败: {e}")
            all_fields_ok = False

    if all_fields_ok:
        print("  ✓ 所有记录字段完整")

    # ================================================================
    # 2. prev_hash 连续性
    # ================================================================
    print("\n[检查 2] prev_hash 链连续性")
    chain_ok = True
    for i, r in enumerate(records, 1):
        if i == 1:
            # 第一条：prev_hash 应为 None 或 "GENESIS"
            if r["prev_hash"] not in (None, "GENESIS", ""):
                print(f"  ✗ 第1条 prev_hash 异常: {r['prev_hash']}")
                chain_ok = False
            else:
                print(f"  ✓ 第1条为创世块 (prev_hash={r['prev_hash']})")
        else:
            expected = records[i-2]["record_hash"]
            actual = r["prev_hash"]
            if actual != expected:
                print(f"  ✗ 第{i}条断链: prev_hash={actual[:16]}..., 期望={expected[:16]}...")
                chain_ok = False
            else:
                print(f"  ✓ 第{i}条链接正确")

    if chain_ok:
        print("  ★ 哈希链从头到尾连续，无断链")

    # ================================================================
    # 3. record_hash 计算验证
    # ================================================================
    print("\n[检查 3] record_hash 计算验证")
    hash_algo_ok = True
    for i, r in enumerate(records, 1):
        prev = r["prev_hash"] if r["prev_hash"] else ""
        join_prev = prev if prev and prev != "GENESIS" else ""
        calculated = hashlib.md5(
            (r["file_hash"] + join_prev + str(r["timestamp"])).encode("utf-8")
        ).hexdigest()
        if calculated != r["record_hash"]:
            print(f"  ✗ 第{i}条 record_hash 不匹配")
            print(f"    记录值: {r['record_hash']}")
            print(f"    计算值: {calculated}")
            hash_algo_ok = False

    if hash_algo_ok:
        print(f"  ✓ 所有 {len(records)} 条 record_hash 计算正确")

    # ================================================================
    # 4. file_hash 验证（文件必须存在）
    # ================================================================
    print("\n[检查 4] file_hash 比对（文件实际存在性）")
    file_ok = True
    for i, r in enumerate(records, 1):
        f = r["file"]
        if not os.path.exists(f):
            print(f"  ⚠ 第{i}条文件不存在: {f}")
        else:
            with open(f, "rb") as fh:
                actual_hash = hashlib.md5(fh.read()).hexdigest()
            if actual_hash != r["file_hash"]:
                print(f"  ✗ 第{i}条 file_hash 不匹配 (文件 {f})")
                print(f"    链上值: {r['file_hash']}")
                print(f"    实际值: {actual_hash}")
                file_ok = False

    if file_ok:
        print(f"  ✓ 所有存在的文件 file_hash 与链上一致")

    # ================================================================
    # 5. 检查普通模块是否能直接写入哈希链
    # ================================================================
    print("\n[检查 5] 写权限安全性")
    dir_name = os.path.dirname(os.path.abspath(CHAIN_FILE))
    chain_path = os.path.abspath(CHAIN_FILE)
    print(f"  链文件绝对路径: {chain_path}")
    print(f"  链文件可写: {os.access(chain_path, os.W_OK)}")

    # 检查 os.makedirs 是否能创建父目录（暴露风险）
    test_dirs = [
        os.path.join(dir_name, "test_mkdir_probe"),
        "/tmp/test_mkdir_probe",
    ]
    for td in test_dirs:
        try:
            os.makedirs(td, exist_ok=True)
            print(f"  ⚠ os.makedirs('{td}') 成功 → 任何模块都可以创建目录")
            os.rmdir(td)
        except PermissionError:
            print(f"  ✓ os.makedirs('{td}') 权限拒绝")
        except Exception as e:
            print(f"  ? os.makedirs('{td}') 异常: {e}")

if __name__ == "__main__":
    verify_chain()
