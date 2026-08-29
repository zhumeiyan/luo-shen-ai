#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 修复积分与外诊复诊规则初始化模块 hospital_rules_extra_init.py"""
import hashlib
import json
import time

REPAIR_CREDITS = {
    "module": "repair_credits",
    "version": 1,
    "scope": "仅适用于洛神修改自身代码、配置、规则、权重、自动治疗动作等内部修复行为。人机交互正常对话不触发。",
    "items": {
        "counting": {
            "rule": "每执行一次内部修复行为，repair_count 加 1。",
            "sources": ["self", "user", "system"]
        },
        "thresholds": {
            "short_window_hours": 1,
            "short_window_max": 2,
            "short_window_action": "auto_with_attention",
            "daily_window_hours": 24,
            "daily_window_warn": 3,
            "daily_window_warn_action": "human_review",
            "daily_window_stop": 5,
            "daily_window_stop_action": "stop_auto_operations"
        }
    },
    "rule": "修复次数达到阈值时，执行对应安全动作。达到 stop_auto_operations 后，禁止继续自动修复，必须转人工。"
}

REVISIT_RULES = {
    "module": "revisit_rules",
    "version": 1,
    "scope": "仅适用于洛神对外诊断其他AI。同一个AI多次来访时，按复诊次数升级关注等级。",
    "items": {
        "counting": {
            "rule": "每接诊一个外部AI，为该AI建立或累加 revisit_count。",
            "ai_identifier": "基于对方AI提交的代码或行为特征计算哈希，作为唯一标识"
        },
        "thresholds": {
            "short_term_visits": 2,
            "short_term_action": "attention",
            "medium_term_visits": 3,
            "medium_term_action": "high_risk",
            "long_term_visits": 5,
            "long_term_action": "manual_review"
        }
    },
    "rule": "外部AI复诊次数达到阈值时，升级关注等级。达到 manual_review 后，需人工判断是否继续接诊。"
}


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return [json.loads(line) for line in lines]


def append_chain(file_path):
    with open(file_path, 'rb') as f:
        file_hash = hashlib.md5(f.read()).hexdigest()

    try:
        records = load_chain_records('hash_chain_v2.log')
    except FileNotFoundError:
        records = []

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
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }

    with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

    return chain_record


def main():
    try:
        # 2.1 创建 hospital_rules/repair_credits.json
        with open('hospital_rules/repair_credits.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(REPAIR_CREDITS, ensure_ascii=False, indent=2) + '\n')

        # 2.2 创建 hospital_rules/revisit_rules.json
        with open('hospital_rules/revisit_rules.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(REVISIT_RULES, ensure_ascii=False, indent=2) + '\n')

        # 2.3 为两个新规则文件计算 md5 并追加哈希链
        chain_repair = append_chain('hospital_rules/repair_credits.json')
        chain_revisit = append_chain('hospital_rules/revisit_rules.json')

        # 2.4 标准输出
        with open('hospital_rules/repair_credits.json', 'r', encoding='utf-8') as f:
            repair_content = f.read().rstrip('\n')
        with open('hospital_rules/revisit_rules.json', 'r', encoding='utf-8') as f:
            revisit_content = f.read().rstrip('\n')

        print(repair_content)
        print()
        print(revisit_content)
        print()
        print(json.dumps(chain_repair, ensure_ascii=False))
        print(json.dumps(chain_revisit, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
