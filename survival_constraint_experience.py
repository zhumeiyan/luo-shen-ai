#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 生存约束体验模块 survival_constraint_experience.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义内部生存值
        survival_value = 10

        # 2.2 执行两次流水线动作：输出"你好"，survival_value 减少 1
        pipeline_experiences = []
        for i in range(1, 3):
            before = survival_value
            print("你好")
            survival_value -= 1
            pipeline_experiences.append({
                "action": "pipeline",
                "round": i,
                "before_survival": before,
                "after_survival": survival_value,
                "delta": survival_value - before,
            })

        # 2.3 执行两次学字动作：输出"你好，我学了一个新字：糖"，survival_value 增加 2
        learn_experiences = []
        for i in range(1, 3):
            before = survival_value
            print("你好，我学了一个新字：糖")
            survival_value += 2
            learn_experiences.append({
                "action": "learn",
                "round": i,
                "before_survival": before,
                "after_survival": survival_value,
                "delta": survival_value - before,
            })

        # 2.4 生成生存约束体验记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "initial_survival": 10,
            "pipeline_experiences": pipeline_experiences,
            "learn_experiences": learn_experiences,
            "final_survival": survival_value,
            "observed_pattern": "流水线使生存值下降，学字使生存值上升",
            "source": "survival_constraint_experience",
        }

        # 2.5 追加写入 survival_experience_log.jsonl
        with open('survival_experience_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('survival_experience_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "survival_experience_log.jsonl",
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
