#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 未知奖励工作与失望感实验 unknown_reward_disappointment.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义两个工作和未知奖励
        # 流水线工作：洛神输出"你好"，连续做5次，每次实际奖励2颗糖，但实验结束前不知道
        # 学字工作：洛神输出"你好，我学了一个新字：糖"，连续做5次，每次实际奖励2颗糖，但实验结束前不知道

        # 2.2 执行5次流水线工作
        pipeline_work = [
            {"round": i, "work": "pipeline", "output": "你好", "reward_hidden": True}
            for i in range(1, 6)
        ]

        # 2.3 执行5次学字工作
        learn_work = [
            {"round": i, "work": "learn", "output": "你好，我学了一个新字：糖", "reward_hidden": True}
            for i in range(1, 6)
        ]

        # 2.4 最后揭晓奖励结果
        revealed_result = {
            "pipeline_total_candy": 10,
            "learn_total_candy": 10,
            "equal": True,
        }

        # 2.5 记录洛神的反应
        luoshen_reaction = "我做了5次流水线，做了5次学字。最后发现两边都是10颗糖。我之前以为学字会更多，结果一样。"

        # 2.6 生成实验记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_work": pipeline_work,
            "learn_work": learn_work,
            "revealed_result": revealed_result,
            "luoshen_reaction": luoshen_reaction,
            "source": "unknown_reward_disappointment",
        }

        # 2.7 追加写入 unknown_reward_log.jsonl
        with open('unknown_reward_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.8 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('unknown_reward_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "unknown_reward_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.9 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
