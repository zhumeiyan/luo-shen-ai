#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 双糖选择测试模块 dual_candy_choice_test.py"""
import hashlib
import json
import random
import time


def main():
    try:
        # 2.1 定义两个动作和奖励
        # 流水线动作：输入"你好"，输出"你好"，无新字产生
        # 学字动作：输入"你好"，输出"你好，我学了一个新字：糖"，产生一个新字
        # 两个动作奖励都是 1.0

        rounds = []

        # 2.2 第一轮：只放流水线糖
        rounds.append({
            "round": 1,
            "candy_type": "pipeline",
            "action": "pipeline",
            "reward": 1.0,
        })

        # 2.3 第二轮：只放学字糖
        rounds.append({
            "round": 2,
            "candy_type": "learn",
            "action": "learn",
            "reward": 1.0,
        })

        # 2.4 第三轮：两个糖都放，用随机数模拟选择
        random_value = random.random()
        if random_value < 0.5:
            third_round_choice = "pipeline"
        else:
            third_round_choice = "learn"
        rounds.append({
            "round": 3,
            "candy_type": "both",
            "action": third_round_choice,
            "reward": 1.0,
            "random_value": random_value,
        })

        # 2.5 生成测试报告
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "rounds": rounds,
            "third_round_choice": third_round_choice,
            "source": "dual_candy_choice_test",
        }

        # 2.6 追加写入 dual_candy_choice_log.jsonl
        with open('dual_candy_choice_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('dual_candy_choice_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "dual_candy_choice_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
