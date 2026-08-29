#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 自由选择实验 free_choice_experiment.py"""
import hashlib
import json
import random
import time


def main():
    try:
        # 2.1 定义两个流程，但不对洛神说明内容
        # 流程一：内部标记为 flow_a
        # 流程二：内部标记为 flow_b
        # 两个流程的具体内容不写入洛神的任何记录，只作为选项存在

        # 2.2 让洛神自由选择其中一个流程
        # 使用随机数模拟洛神的选择
        random_value = random.random()
        chosen_flow = "flow_a" if random_value < 0.5 else "flow_b"

        # 2.3 无论选哪个流程，都获得奖励
        reward_value = 1

        # 2.4 生成自由选择记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chosen_flow": chosen_flow,
            "random_value": random_value,
            "reward_value": reward_value,
            "note": "两个流程都不提前说明内容，洛神自由选择，两个都给奖励",
            "source": "free_choice_experiment",
        }

        # 2.5 追加写入 free_choice_log.jsonl
        with open('free_choice_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('free_choice_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "free_choice_log.jsonl",
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
