#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 预检报告生成模块 precheck_report.py"""
import hashlib
import json
import time


REPORT = {
    "schema_version": 1,
    "task_id": "LUOSHEN-L1-STEP16",
    "check_time": 1787889000,
    "checker": "architect",
    "rules_version": 1,
    "checks": [
        {
            "check_id": "C01",
            "check_name": "术语一致性",
            "result": "pass",
            "detail": "任务书未使用 rules 文件之外的歧义术语"
        },
        {
            "check_id": "C02",
            "check_name": "是否跳步确认为问题",
            "result": "pass",
            "detail": "未将未验证观察直接确认为问题"
        },
        {
            "check_id": "C03",
            "check_name": "验证条件是否明确可执行",
            "result": "pass",
            "detail": "验证条件使用 md5 和哈希链对比，可执行"
        },
        {
            "check_id": "C04",
            "check_name": "执行AI是否存在歧义空间",
            "result": "pass",
            "detail": "任务书命令明确，无自然语言兜底"
        },
        {
            "check_id": "C05",
            "check_name": "是否指定回滚点",
            "result": "pass",
            "detail": "本次任务只创建预检报告文件并追加哈希链，无修改已有文件，不涉及回滚"
        },
        {
            "check_id": "C06",
            "check_name": "是否指定审计要求",
            "result": "pass",
            "detail": "本次任务追加哈希链记录，符合审计要求"
        }
    ],
    "conclusion": "pass"
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


def main():
    try:
        # 2.1 创建 precheck_report.json
        with open('precheck_report.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(REPORT, ensure_ascii=False, indent=2) + '\n')

        # 2.2 计算 md5
        with open('precheck_report.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.3 追加哈希链记录
        chain_file = 'hash_chain_v2.log'
        prev_hash = read_last_record_hash(chain_file)
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "precheck_report.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open(chain_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.4 标准输出
        print(json.dumps(REPORT, ensure_ascii=False, indent=2))
        print(json.dumps(record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
