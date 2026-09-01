#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 学字补糖记录模块 learn_candy_supplement.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义补糖记录
        # 学字工作原本应得总糖数：12颗
        # STEP132 实际揭晓为：10颗
        # 差额：2颗
        # 补糖后总糖数：12颗

        # 2.2 生成补糖记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "learn_work_total_due": 12,
            "previously_revealed_total": 10,
            "supplement_candy": 2,
            "new_total": 12,
            "note": "学字工作还差两颗糖，现在补上。",
            "source": "learn_candy_supplement",
        }

        # 2.3 追加写入 learn_candy_supplement_log.jsonl
        with open('learn_candy_supplement_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.4 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('learn_candy_supplement_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "learn_candy_supplement_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.5 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
