#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 黑匣子废弃标记模块 blackbox_deprecate.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 创建 blackbox_deprecated.json
        content = {
            "schema_version": 1,
            "module": "blackbox_deprecated",
            "version": 1,
            "description": "黑匣子相关文件已废弃，不再作为洛神系统有效组件。保留历史记录仅供审计，不删除任何文件。",
            "deprecated_files": [
                "blackbox_experiment_log.jsonl",
                "blackbox_before_after.py",
                "schrodinger_blackbox.py",
                "schrodinger_blackbox_log.jsonl",
                "blackbox_and_hetero_test.py",
                "blackbox_hetero_log.jsonl"
            ],
            "status": "deprecated"
        }
        with open('blackbox_deprecated.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(content, ensure_ascii=False, indent=2) + '\n')

        # 2.2 计算 md5
        with open('blackbox_deprecated.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.3 追加哈希链记录
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            clines = []
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "blackbox_deprecated.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.4 标准输出
        with open('blackbox_deprecated.json', 'r', encoding='utf-8') as f:
            print(f.read().rstrip('\n'))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
