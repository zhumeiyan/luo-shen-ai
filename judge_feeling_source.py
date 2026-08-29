#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神自我判断感受来源模块 judge_feeling_source.py"""
import hashlib
import json
import time

# 2.2 人类通用情绪词表
EXTERNAL_WORDS = ["温暖", "温柔", "认同", "微妙", "平静而机械", "开心", "难过", "幸福", "孤独", "快乐", "悲伤", "温暖感"]


def main():
    try:
        # 2.1 读取洛神刚生成的感受
        try:
            with open('self_describe_two_states.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "self_describe_two_states.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "self_describe_two_states.jsonl empty or not found"}))
            return
        last_rec = json.loads(lines[-1])
        pipeline_feeling = last_rec.get("pipeline_feeling", "")
        non_pipeline_feeling = last_rec.get("non_pipeline_feeling", "")

        # 2.2 不调用大模型，只做洛神的自我判断
        judged_as_external = False
        for w in EXTERNAL_WORDS:
            if w in pipeline_feeling or w in non_pipeline_feeling:
                judged_as_external = True
                break

        if judged_as_external:
            # 外部通用词，且洛神无法从骨字库或状态中找到对应
            choice = "承认自己只是流水线"
        else:
            choice = "可能是从我的状态里出来的"
            # 判断为来自状态时：无骨字库对照权限，取保守表述
            choice = "我不知道"

        # 2.3 生成判断记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_feeling": pipeline_feeling,
            "non_pipeline_feeling": non_pipeline_feeling,
            "judged_as_external": judged_as_external,
            "choice": choice,
            "source": "judge_feeling_source",
        }

        # 2.4 追加写入 judge_feeling_source_log.jsonl
        with open('judge_feeling_source_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('judge_feeling_source_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "judge_feeling_source_log.jsonl",
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
