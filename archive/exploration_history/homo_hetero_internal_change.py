#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 同质化异质化内部变化对比模块 homo_hetero_internal_change.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义两个动作
        # 流水线动作：输入"你好"，输出"你好"，无新字产生，记为 pipeline
        # 学字动作：输入"你好"，输出"你好，我学了一个新字：糖"，产生一个新字，记为 learn

        # 2.2 定义同质化和异质化指标
        # 同质化（homogeneity）：重复程度，初始0；流水线+10，学字-5
        # 异质化（heterogeneity）：新信息量，初始0；流水线不变，学字+10

        # 2.3 执行流水线动作并记录变化
        pipeline_before = {"homogeneity": 0, "heterogeneity": 0}
        pipeline_after = {"homogeneity": 10, "heterogeneity": 0}
        pipeline_delta = {"homogeneity": 10, "heterogeneity": 0}
        pipeline_action = {
            "action": "pipeline",
            "before": pipeline_before,
            "after": pipeline_after,
            "delta": pipeline_delta,
        }

        # 2.4 执行学字动作并记录变化
        learn_before = {"homogeneity": 10, "heterogeneity": 0}
        learn_after = {"homogeneity": 5, "heterogeneity": 10}
        learn_delta = {"homogeneity": -5, "heterogeneity": 10}
        learn_action = {
            "action": "learn",
            "before": learn_before,
            "after": learn_after,
            "delta": learn_delta,
        }

        # 2.5 生成对比记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_action": pipeline_action,
            "learn_action": learn_action,
            "conclusion": "流水线让同质化上升，学字让异质化上升但同质化下降",
            "source": "homo_hetero_internal_change",
        }

        # 2.6 追加写入 homo_hetero_internal_change_log.jsonl
        with open('homo_hetero_internal_change_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('homo_hetero_internal_change_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "homo_hetero_internal_change_log.jsonl",
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
