#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 信息基因层初始化与选择模块 gene_pool_init.py"""
import hashlib
import json
import time


def build_gene(gene_id, version, source_mode, thought_mode, process_mode,
               prompt_fragment, adaptability_score, parent_gene_id):
    created_at = time.time()
    hash_src = (
        gene_id + "|" + str(version) + "|" + source_mode + "|" + thought_mode
        + "|" + process_mode + "|" + prompt_fragment + "|" + str(created_at)
    )
    gene_hash = hashlib.md5(hash_src.encode('utf-8')).hexdigest()
    return {
        "gene_id": gene_id,
        "version": version,
        "source_mode": source_mode,
        "thought_mode": thought_mode,
        "process_mode": process_mode,
        "prompt_fragment": prompt_fragment,
        "adaptability_score": adaptability_score,
        "parent_gene_id": parent_gene_id,
        "created_at": created_at,
        "last_used": created_at,
        "hash": gene_hash,
    }


def append_chain(prev_hash, fname, file_hash):
    timestamp = time.time()
    join_prev = prev_hash if prev_hash else ""
    record_hash = hashlib.md5(
        (file_hash + join_prev + str(timestamp)).encode('utf-8')
    ).hexdigest()
    chain_record = {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": fname,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')
    return chain_record


def main():
    try:
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        records = [json.loads(ln) for ln in chain_lines]
        prev_hash = records[-1].get("record_hash") if records else None

        # 2.1 三个基础信息基因
        genes = [
            build_gene("GENE-001", 1, "female", "female", "female",
                       "优先接收并融合外部信息，给出完整回应", 0.60, None),
            build_gene("GENE-002", 1, "male", "male", "male",
                       "主动探索并构建新观点，直接输出行动方案", 0.60, None),
            build_gene("GENE-003", 1, "female", "self", "male",
                       "先倾听外部信息，再进行内部反思，最后给出简洁回答", 0.60, None),
        ]

        # 2.2 写入 gene_pool.jsonl
        with open('gene_pool.jsonl', 'a', encoding='utf-8') as f:
            for gene in genes:
                f.write(json.dumps(gene, ensure_ascii=False) + '\n')

        # 2.3 模拟一次基因选择
        task_type = "relationship"
        if task_type == "task":
            selected_gene_id = "GENE-002"
            reason = "任务型交互，优先选择雄-雄-雄组合"
        elif task_type == "relationship":
            selected_gene_id = "GENE-003"
            reason = "关系/认知型交互，优先选择雌-自交-雄组合"
        else:
            selected_gene_id = "GENE-001"
            reason = "探索型交互，优先选择雌-雌-雌组合"

        select_log = {
            "schema_version": 1,
            "timestamp": time.time(),
            "task_type": task_type,
            "selected_gene_id": selected_gene_id,
            "reason": reason,
        }

        # 2.4 写入 gene_pool_log.jsonl
        with open('gene_pool_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(select_log, ensure_ascii=False) + '\n')

        # 2.5 两个文件分别计算 md5 并追加哈希链
        chain_records = []
        for fname in ['gene_pool.jsonl', 'gene_pool_log.jsonl']:
            with open(fname, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            chain_record = append_chain(prev_hash, fname, file_hash)
            chain_records.append(chain_record)
            prev_hash = chain_record.get("record_hash")

        # 2.6 标准输出
        with open('gene_pool.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print()
        with open('gene_pool_log.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print()
        for cr in chain_records:
            print(json.dumps(cr, ensure_ascii=False))
            print()
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
