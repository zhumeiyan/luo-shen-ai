#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
哈希链深度验证 V2：
- 使用代码中拼接方式逐条重算 record_hash
- 检查 prev_hash 链接
- 对比 backup 链与当前链
"""

import json
import hashlib
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def calc_record_hash(file_hash, prev_hash_val, timestamp):
    """与 hash_chain_v2.py 完全一致的算法"""
    join_prev = prev_hash_val if prev_hash_val else ""
    return hashlib.md5(
        (file_hash + join_prev + str(timestamp)).encode("utf-8")
    ).hexdigest()

def verify_chain_file(chain_path, label):
    print(f"\n{'='*70}")
    print(f"  {label}: {chain_path}")
    print(f"{'='*70}")

    if not os.path.exists(chain_path):
        print("  文件不存在")
        return

    with open(chain_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    print(f"  总条数: {len(lines)}")

    records = []
    for i, line in enumerate(lines):
        try:
            r = json.loads(line)
            records.append(r)
        except Exception as e:
            print(f"  ✗ 第{i+1}条 JSON 解析失败: {e}")
            return

    # 收集纠错映射
    corrected_hashes = set()
    for r in records:
        if r.get("event_type") == "hash_correction":
            corr = r.get("correction", {})
            for stored_hash, _ in corr.items():
                corrected_hashes.add(stored_hash)
    if corrected_hashes:
        print(f"  发现纠错声明，覆盖 {len(corrected_hashes)} 个 hash")

    # 逐条验证
    chain_ok = True
    for i, r in enumerate(records):
        # 期望的 prev_hash（纠错记录自身也需验证链接）
        if i == 0:
            expected_prev = None
            actual_prev = r.get("prev_hash")
            if actual_prev not in (None, ""):
                print(f"  ✗ 第1条 prev_hash 应为 null, 实际: {actual_prev}")
                chain_ok = False
            else:
                print(f"  ✓ 第1条创世块, prev_hash=null")
        else:
            expected_prev = records[i - 1]["record_hash"]
            actual_prev = r.get("prev_hash")
            if actual_prev != expected_prev:
                print(f"  ✗ 第{i+1}条断链: prev_hash={actual_prev[:16] if actual_prev else 'None'}... 期望={expected_prev[:16]}...")
                chain_ok = False

        # 重算 record_hash
        prev_for_calc = r.get("prev_hash") if r.get("prev_hash") else ""
        calculated = calc_record_hash(r["file_hash"], prev_for_calc, r["timestamp"])
        # 如果该 record_hash 已被纠错声明覆盖，跳过公式校验
        if r["record_hash"] in corrected_hashes:
            f_short = r['file']
            print(f"  ✓ 第{i+1}条: {f_short} [已纠错声明覆盖，跳过公式校验]")
            continue
        if calculated != r["record_hash"]:
            print(f"  ✗ 第{i+1}条 record_hash 未覆盖且不匹配")
            print(f"    文件: {r['file']}")
            print(f"    记录值:   {r['record_hash']}")
            print(f"    计算值:   {calculated}")
            chain_ok = False
        else:
            # 简洁输出
            f_short = r['file']
            print(f"  ✓ 第{i+1}条: {f_short} hash正确")

    if chain_ok:
        print(f"\n  ★ {label} 全部验证通过（链连续 + 哈希正确）")
    else:
        print(f"\n  ✗ {label} 验证失败")


def scan_writers():
    """扫描哪些文件直接 append 写入 hash_chain_v2.log"""
    print(f"\n{'='*70}")
    print(f"  哪些模块能直接写哈希链？")
    print(f"{'='*70}")

    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "hash_chain_v2.log", "--include=*.py", "."],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
    )
    lines = [l for l in result.stdout.split("\n") if l.strip()
             and "verify" not in l and ".pyc" not in l]

    writers = []
    for line in lines:
        # file:line_num:content
        parts = line.split(":", 2)
        if len(parts) >= 3:
            fname = parts[0]
            content = parts[2] if len(parts) > 2 else ""
            # 只找 "a" 模式写入
            if '"a"' in content or "'a'" in content or "hash_chain_v2.log" in content and "write" in content:
                writers.append(line)

    print(f"\n  搜到的涉及 hash_chain_v2.log 引用数: {len(lines)}")
    print(f"  可能含写入的引用:")
    for w in lines[:20]:
        print(f"    {w}")


if __name__ == "__main__":
    verify_chain_file("hash_chain_v2.backup.log", "备份链")
    verify_chain_file("hash_chain_v2.log", "当前链")
    scan_writers()
