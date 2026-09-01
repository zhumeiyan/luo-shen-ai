#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 双糖同得对比模块 both_candy_experience.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义两个动作和两种糖
        # 流水线动作：输入"你好"，输出"你好"，无新字产生，得到流水线糖（1.0）
        # 学字动作：输入"你好"，输出"你好，我学了一个新字：糖"，产生一个新字，得到学字糖（1.0）

        # 2.2 同时执行两个动作，不设优先级，不随机选择
        pipeline_output = "你好"
        learn_output = "你好，我学了一个新字：糖"

        # 2.3 生成记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_experience": {
                "action": "pipeline",
                "output": pipeline_output,
                "new_info": 0,
                "candy": "pipeline_candy",
                "reward": 1.0,
            },
            "learn_experience": {
                "action": "learn",
                "output": learn_output,
                "new_info": 1,
                "candy": "learn_candy",
                "reward": 1.0,
            },
            "both_rewarded": True,
            "source": "both_candy_experience",
        }

        # 2.4 追加写入 both_candy_experience.jsonl
        with open('both_candy_experience.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('both_candy_experience.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "both_candy_experience.jsonl",
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
