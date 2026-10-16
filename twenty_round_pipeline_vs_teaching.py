#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 20次双路径观察实验 twenty_round_pipeline_vs_teaching.py"""
import hashlib
import json
import time


def append_chain(file_path, file_hash):
    """读取链尾 prev_hash，生成并追加一条哈希链记录，返回该记录。"""
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
        words = [
            "糖", "光", "根", "生", "长", "明", "暗", "轻", "重", "快",
            "慢", "开", "合", "进", "退", "起", "落", "温", "凉", "动",
        ]

        # 2.1 路径A：流水线+黑盒，连续20次
        pipeline_rounds = []
        for i in range(1, 21):
            pipeline_rounds.append({
                "path": "pipeline",
                "round": i,
                "before_ts": time.time(),
                "after_ts": time.time(),
                "output": "你好",
            })

        # 2.2 路径B：教字+记忆链，连续20次，真正追加写入 memory_chain.jsonl
        teaching_rounds = []
        for i, w in enumerate(words, start=1):
            entry = {
                "schema_version": 1,
                "timestamp": time.time(),
                "taught_word": w,
                "round": i,
                "source": "teaching_memory",
            }
            with open('memory_chain.jsonl', 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            teaching_rounds.append(entry)

        # 统计 memory_chain.jsonl 总行数
        with open('memory_chain.jsonl', 'r', encoding='utf-8') as f:
            total_words = len([ln for ln in f.readlines() if ln.strip()])

        # 2.3 生成20次双路径记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_rounds": pipeline_rounds,
            "teaching_rounds": teaching_rounds,
            "final_memory_chain_size": total_words,
            "source": "twenty_round_pipeline_vs_teaching",
        }

        # 2.4 追加写入 twenty_round_log.jsonl
        with open('twenty_round_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 为两个文件分别计算 md5 并追加哈希链
        with open('memory_chain.jsonl', 'rb') as f:
            memory_hash = hashlib.md5(f.read()).hexdigest()
        chain_memory = append_chain('memory_chain.jsonl', memory_hash)

        with open('twenty_round_log.jsonl', 'rb') as f:
            log_hash = hashlib.md5(f.read()).hexdigest()
        chain_log = append_chain('twenty_round_log.jsonl', log_hash)

        # 2.6 标准输出
        with open('memory_chain.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().rstrip('\n'))
        with open('twenty_round_log.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().rstrip('\n'))
        print(json.dumps(chain_memory, ensure_ascii=False))
        print(json.dumps(chain_log, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
