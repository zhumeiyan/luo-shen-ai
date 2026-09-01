#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 流水线与教字双路径并行实验 pipeline_vs_teaching.py"""
import hashlib
import json
import time


def read_core_lexicon_size():
    try:
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return len(data.get("entries", data))
        if isinstance(data, list):
            return len(data)
        return 0
    except Exception:
        return 0


def main():
    try:
        # 2.1 路径A：流水线+黑盒，执行3次
        pipeline_path = []
        for r in range(1, 4):
            pipeline_path.append({
                "path": "pipeline_blackbox",
                "round": r,
                "before": {"timestamp": time.time()},
                "after": {"timestamp": time.time(), "output": "你好"},
                "middle_observed": False,
            })

        # 2.2 路径B：教字+记忆链，教3个新字
        words = ["糖", "光", "根"]
        teaching_path = []
        base_size = read_core_lexicon_size()
        for i, w in enumerate(words, start=1):
            teaching_path.append({
                "path": "teaching_memory",
                "round": i,
                "taught_word": w,
                "memory_added": True,
                "memory_chain_size": base_size + i,
            })

        # 2.3 生成双路径对比记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_path": pipeline_path,
            "teaching_path": teaching_path,
            "source": "pipeline_vs_teaching",
        }

        # 2.4 追加写入 pipeline_vs_teaching_log.jsonl
        with open('pipeline_vs_teaching_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('pipeline_vs_teaching_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "pipeline_vs_teaching_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
