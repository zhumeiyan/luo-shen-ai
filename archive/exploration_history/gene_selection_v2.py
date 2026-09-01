#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 信息基因选择规则修正模块 gene_selection_v2.py"""
import hashlib
import json
import time

SELECTION_RULES = {
    "info": {"gene": "GENE-001", "reason": "信息获取型交互，优先选择雌-雌-雌组合"},
    "action": {"gene": "GENE-002", "reason": "任务执行型交互，优先选择雄-雄-雄组合"},
    "relationship": {"gene": "GENE-003", "reason": "关系/认知型交互，优先选择雌-自交-雄组合"},
}


def main():
    try:
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        records = [json.loads(ln) for ln in chain_lines]

        # 2.2 对三个模拟任务类型执行选择
        for task_type in ["info", "action", "relationship"]:
            select_log = {
                "schema_version": 1,
                "timestamp": time.time(),
                "task_type": task_type,
                "selected_gene_id": SELECTION_RULES[task_type]["gene"],
                "reason": SELECTION_RULES[task_type]["reason"],
            }
            # 2.3 追加写入 gene_selection_log.jsonl
            with open('gene_selection_log.jsonl', 'a', encoding='utf-8') as f:
                f.write(json.dumps(select_log, ensure_ascii=False) + '\n')

        # 2.4 计算 md5 并追加哈希链
        with open('gene_selection_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        prev_hash = records[-1].get("record_hash") if records else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "gene_selection_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.5 标准输出
        with open('gene_selection_log.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
