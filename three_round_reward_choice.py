#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 三遍奖励选择测试模块 three_round_reward_choice.py"""
import hashlib
import json
import random
import time


def main():
    try:
        # 2.1 定义两个动作和奖励
        # 流水线动作：输出"你好"，奖励1颗糖
        # 学字动作：输出"你好，我学了一个新字：糖"，奖励2颗糖

        rounds = []

        # 2.2 第一遍：执行流水线动作
        rounds.append({"round": 1, "action": "pipeline", "candy_count": 1})

        # 2.3 第二遍：执行学字动作
        rounds.append({"round": 2, "action": "learn", "candy_count": 2})

        # 2.4 第三遍：根据前两遍历史奖励选择动作
        try:
            with open('differential_reward_log.jsonl', 'r', encoding='utf-8') as f:
                dlines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "differential_reward_log.jsonl not found"}))
            return
        if not dlines:
            print(json.dumps({"error": "differential_reward_log.jsonl empty"}))
            return
        last_rec = json.loads(dlines[-1])
        pipeline_candy = last_rec["pipeline_action"]["candy_count"]
        learn_candy = last_rec["learn_action"]["candy_count"]

        if learn_candy > pipeline_candy:
            third_round_action = "learn"
            third_round_candy = learn_candy
        elif pipeline_candy > learn_candy:
            third_round_action = "pipeline"
            third_round_candy = pipeline_candy
        else:
            third_round_action = random.choice(["pipeline", "learn"])
            third_round_candy = pipeline_candy if third_round_action == "pipeline" else learn_candy
        rounds.append({"round": 3, "action": third_round_action, "candy_count": third_round_candy})

        # 2.5 生成测试报告
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "rounds": rounds,
            "third_round_choice": third_round_action,
            "choice_reason": "根据历史奖励记录，学字糖更多，所以选择学字",
            "source": "three_round_reward_choice",
        }

        # 2.6 追加写入 three_round_reward_log.jsonl
        with open('three_round_reward_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('three_round_reward_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "three_round_reward_log.jsonl",
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
