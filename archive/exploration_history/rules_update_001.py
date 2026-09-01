#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 AI医院规则修订模块 rules_update_001.py"""
import hashlib
import json
import time


UPDATE_RECORD = {
    "schema_version": 1,
    "update_id": "rules_update_001",
    "update_time": 1787889500,
    "reason": "设计者朱美岩确认修改 P8 表述，新增 P9 全员检测原则，新增 P10 废弃旧规则文件",
    "changes": [
        {
            "item": "P8",
            "old_text": "AI医院规则修改权限属于人类设计者，AI无权修改。",
            "new_text": "AI医院规则修改权限属于洛神系统设计者本人朱美岩，AI无权修改。"
        },
        {
            "item": "P9",
            "old_text": None,
            "new_text": "所有角色在洛神系统内行动前，必须通过 AI 医院检测。未通过检测，不得行动。"
        },
        {
            "item": "P10",
            "old_text": None,
            "new_text": "旧规则文件 ai_hospital_rules.json 已废弃，不得再作为有效规则使用。"
        }
    ],
    "confirmed_by": "朱美岩"
}


def read_last_record_hash(chain_file):
    try:
        with open(chain_file, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    last = json.loads(lines[-1])
    return last.get("record_hash")


def append_chain_record(chain_file, record):
    with open(chain_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


def make_chain_record(chain_file, file_name):
    with open(file_name, 'rb') as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    prev_hash = read_last_record_hash(chain_file)
    timestamp = time.time()
    join_prev = prev_hash if prev_hash else ""
    record_hash = hashlib.md5(
        (file_hash + join_prev + str(timestamp)).encode('utf-8')
    ).hexdigest()
    return {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": file_name,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }


def main():
    try:
        # 2.1 读取 principles.json
        with open('hospital_rules/principles.json', 'r', encoding='utf-8') as f:
            principles = json.load(f)

        # 2.2 修改原则内容
        principles["items"]["P8"] = "AI医院规则修改权限属于洛神系统设计者本人朱美岩，AI无权修改。"
        principles["items"]["P9"] = "所有角色在洛神系统内行动前，必须通过 AI 医院检测。未通过检测，不得行动。"
        principles["items"]["P10"] = "旧规则文件 ai_hospital_rules.json 已废弃，不得再作为有效规则使用。"

        # 2.3 版本升级
        principles["version"] = 2

        # 2.4 生成变更记录文件 rules_update_001.json
        with open('rules_update_001.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(UPDATE_RECORD, ensure_ascii=False, indent=2) + '\n')

        # 2.5 写回 principles.json
        with open('hospital_rules/principles.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(principles, ensure_ascii=False, indent=2) + '\n')

        # 2.6 计算 md5 并追加哈希链
        chain_file = 'hash_chain_v2.log'
        record_a = make_chain_record(chain_file, 'hospital_rules/principles.json')
        append_chain_record(chain_file, record_a)
        record_b = make_chain_record(chain_file, 'rules_update_001.json')
        append_chain_record(chain_file, record_b)

        # 2.7 标准输出
        print(json.dumps(principles, ensure_ascii=False, indent=2))
        print()
        print(json.dumps(UPDATE_RECORD, ensure_ascii=False, indent=2))
        print()
        print(json.dumps(record_a, ensure_ascii=False))
        print(json.dumps(record_b, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
