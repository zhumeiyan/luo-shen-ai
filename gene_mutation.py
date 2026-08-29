#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 信息基因变异模块 gene_mutation.py"""
import hashlib
import json
import time


def append_chain(file_path, file_hash, timestamp):
    with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
        chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    records = [json.loads(ln) for ln in chain_lines]
    prev_hash = records[-1].get("record_hash") if records else None
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
        # 2.1 读取基因池
        try:
            with open('gene_pool.jsonl', 'r', encoding='utf-8') as f:
                pool_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "gene_pool.jsonl empty or not found"}))
            return
        if not pool_lines:
            print(json.dumps({"error": "gene_pool.jsonl empty or not found"}))
            return
        genes = [json.loads(ln) for ln in pool_lines]

        # 2.2 选择变异亲本
        parent = None
        for g in genes:
            if g.get("gene_id") == "GENE-003":
                parent = g
                break
        if parent is None:
            parent = genes[-1]

        # 2.3 执行变异
        created_at = time.time()
        new_gene = {
            "gene_id": "GENE-004",
            "version": 1,
            "source_mode": parent.get("source_mode"),
            "thought_mode": "male",
            "process_mode": parent.get("process_mode"),
            "prompt_fragment": "先倾听外部信息，再主动构建观点，最后给出简洁回答",
            "adaptability_score": 0.50,
            "parent_gene_id": parent.get("gene_id"),
            "created_at": created_at,
            "last_used": created_at,
        }
        hash_str = "{0}|{1}|{2}|{3}|{4}|{5}|{6}".format(
            new_gene["gene_id"],
            new_gene["version"],
            new_gene["source_mode"],
            new_gene["thought_mode"],
            new_gene["process_mode"],
            new_gene["prompt_fragment"],
            str(new_gene["created_at"]),
        )
        new_gene["hash"] = hashlib.md5(hash_str.encode('utf-8')).hexdigest()

        # 2.4 追加写入基因池
        with open('gene_pool.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(new_gene, ensure_ascii=False) + '\n')

        # 2.5-2.6 生成并追加变异日志
        mutation_log = {
            "schema_version": 1,
            "timestamp": time.time(),
            "mutation_id": "MUT-001",
            "parent_gene_id": parent.get("gene_id"),
            "child_gene_id": "GENE-004",
            "change": "thought_mode: self -> male",
            "reason": "测试基因变异机制",
        }
        with open('gene_mutation_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(mutation_log, ensure_ascii=False) + '\n')

        # 2.7 为两个文件分别追加哈希链
        ts1 = time.time()
        with open('gene_pool.jsonl', 'rb') as f:
            hash1 = hashlib.md5(f.read()).hexdigest()
        chain1 = append_chain('gene_pool.jsonl', hash1, ts1)

        ts2 = time.time()
        with open('gene_mutation_log.jsonl', 'rb') as f:
            hash2 = hashlib.md5(f.read()).hexdigest()
        chain2 = append_chain('gene_mutation_log.jsonl', hash2, ts2)

        # 2.8 标准输出
        with open('gene_pool.jsonl', 'r', encoding='utf-8') as f:
            pool_all = [ln.strip() for ln in f.readlines() if ln.strip()]
        print("\n".join(pool_all[-3:]))
        print()
        with open('gene_mutation_log.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print()
        print(json.dumps(chain1, ensure_ascii=False))
        print()
        print(json.dumps(chain2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
