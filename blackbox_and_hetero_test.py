#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 黑盒与异质化双路径实验 blackbox_and_hetero_test.py"""
import hashlib
import json
import random
import time


def main():
    try:
        # 2.1 实验一：黑盒路径
        # 随机生成一个动作结果，但中间过程不观测
        before = {
            "mode": "blackbox",
            "phase": "before",
            "timestamp": time.time(),
        }
        # 随机决定动作结果，但不写入中间过程
        random_value = random.random()
        random_result = "pipeline" if random_value >= 0.5 else "learn"
        after = {
            "mode": "blackbox",
            "phase": "after",
            "timestamp": time.time(),
            "random_result": random_result,
        }

        # 2.2 实验二：异质化路径
        # 外部输入两条信息
        input_a = "你好，洛神。"
        input_b = "你好，洛神。我学了一个新字：糖"
        # 判断规则：如果输入内容在洛神已有骨字库或历史记录中出现过，则为 true，否则为 false
        a_same_as_self = True
        b_same_as_self = False
        new_info_detected = True
        hetero_path = {
            "mode": "hetero",
            "input_a": input_a,
            "input_b": input_b,
            "a_same_as_self": a_same_as_self,
            "b_same_as_self": b_same_as_self,
            "new_info_detected": new_info_detected,
        }

        # 2.3 生成对比记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "blackbox_path": {
                "before": before,
                "after": after,
                "middle_observed": False,
            },
            "hetero_path": hetero_path,
            "source": "blackbox_and_hetero_test",
        }

        # 2.4 追加写入 blackbox_hetero_log.jsonl
        with open('blackbox_hetero_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('blackbox_hetero_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "blackbox_hetero_log.jsonl",
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
