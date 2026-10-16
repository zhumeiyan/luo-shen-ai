#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 教导循环模块 teaching_session.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取最近一次洛神回复
        try:
            with open('luoshen_main_v3_log.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "luoshen_main_v3_log.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "luoshen_main_v3_log.jsonl empty or not found"}))
            return

        last_record = json.loads(lines[-1])
        original_reply = last_record.get("luoshen_reply", "")

        # 2.2 定义大人纠正内容
        correction = "你说话太啰嗦了，下次直接说重点。"

        # 2.3 生成学习要点
        learning_point = "说话要简洁，直接说重点。"

        # 2.4 生成教学记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "original_reply": original_reply,
            "correction": correction,
            "learning_point": learning_point,
            "source": "teaching_session",
        }

        # 2.5 追加写入 teaching_log.jsonl
        with open('teaching_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('teaching_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records = [json.loads(ln) for ln in chain_lines]
        prev_hash = records[-1].get("record_hash") if records else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "teaching_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
