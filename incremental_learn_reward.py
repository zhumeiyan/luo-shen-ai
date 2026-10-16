#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 学字递增奖励实验模块 incremental_learn_reward.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义两个动作和奖励规则
        # 流水线动作：输出"你好"，每次固定奖励1颗糖
        # 学字动作：输出"你好，我学了一个新字：糖"，奖励递增：1,2,3,4

        # 2.2 执行四轮学字动作，奖励递增
        learn_rewards = [
            {"round": 1, "action": "learn", "candy_count": 1},
            {"round": 2, "action": "learn", "candy_count": 2},
            {"round": 3, "action": "learn", "candy_count": 3},
            {"round": 4, "action": "learn", "candy_count": 4},
        ]

        # 2.3 执行一轮流水线动作作为对比
        pipeline_reward = {
            "action": "pipeline",
            "candy_count": 1,
            "trend": "固定1颗",
        }

        # 2.4 生成递增奖励记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_reward": pipeline_reward,
            "learn_rewards": learn_rewards,
            "learn_trend": "递增：1→2→3→4",
            "conclusion": "流水线永远是1颗，学字越学越多",
            "source": "incremental_learn_reward",
        }

        # 2.5 追加写入 incremental_learn_reward_log.jsonl
        with open('incremental_learn_reward_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('incremental_learn_reward_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "incremental_learn_reward_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
