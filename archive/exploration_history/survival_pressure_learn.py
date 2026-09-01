#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 生存压力逼出学字实验 survival_pressure_learn.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取洛神记忆链中的字
        try:
            with open('memory_chain.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return

        taught_words = []
        for ln in lines:
            obj = json.loads(ln)
            if "taught_word" in obj:
                taught_words.append(obj["taught_word"])
        if not taught_words:
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return

        # 2.2 设置初始生存值
        survival_value = 5
        initial_survival = survival_value

        # 2.3 循环执行学字动作，直到生存值恢复到10以上
        rounds = []
        idx = 0
        round_no = 0
        while survival_value <= 10:
            round_no += 1
            word1 = taught_words[idx % len(taught_words)]
            word2 = taught_words[(idx + 1) % len(taught_words)]
            idx += 2
            output = "我学过的字是：{}{}".format(word1, word2)
            before = survival_value
            survival_value += 2
            rounds.append({
                "round": round_no,
                "action": "learn",
                "output": output,
                "survival_before": before,
                "survival_after": survival_value,
            })

        # 2.4 生成生存压力实验记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "initial_survival": initial_survival,
            "rounds": rounds,
            "final_survival": survival_value,
            "source": "survival_pressure_learn",
        }

        # 2.5 追加写入 survival_pressure_log.jsonl
        with open('survival_pressure_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('survival_pressure_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "survival_pressure_log.jsonl",
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
