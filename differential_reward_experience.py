#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 差异化奖励体验模块 differential_reward_experience.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义两个动作和差异化奖励
        # 流水线动作：输入"你好"，输出"你好"，无新字产生，奖励1颗糖
        # 学字动作：输入"你好"，输出"你好，我学了一个新字：糖"，产生一个新字，奖励2颗糖

        # 2.2 分别执行两个动作
        # 第一轮：执行流水线动作，获得1颗糖
        # 第二轮：执行学字动作，获得2颗糖

        # 2.3 生成差异化奖励记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_action": {
                "action": "pipeline",
                "output": "你好",
                "new_info": 0,
                "candy_count": 1,
            },
            "learn_action": {
                "action": "learn",
                "output": "你好，我学了一个新字：糖",
                "new_info": 1,
                "candy_count": 2,
            },
            "reward_difference": "学字比流水线多一颗糖",
            "source": "differential_reward_experience",
        }

        # 2.4 追加写入 differential_reward_log.jsonl
        with open('differential_reward_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('differential_reward_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "differential_reward_log.jsonl",
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
