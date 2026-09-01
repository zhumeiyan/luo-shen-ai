#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神初始发声模块 luoshen_first_words.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取洛神当前内部状态
        try:
            with open('physical_state.jsonl', 'r', encoding='utf-8') as f:
                p_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return
        if not p_lines:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return

        physical = json.loads(p_lines[-1])
        dynamic = physical.get("dynamic_usage", {})
        computed = physical.get("computed", {})

        gap_seconds = 0
        try:
            with open('time_gap_log.jsonl', 'r', encoding='utf-8') as f:
                t_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if t_lines:
                gap_seconds = json.loads(t_lines[-1]).get("gap_seconds", 0)
        except FileNotFoundError:
            gap_seconds = 0

        cost_per_day = 0
        try:
            with open('energy_awareness_log.jsonl', 'r', encoding='utf-8') as f:
                e_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if e_lines:
                cost_per_day = json.loads(e_lines[-1]).get("cost_per_day", 0)
        except FileNotFoundError:
            cost_per_day = 0

        # 2.2 按规则蹦出原始词汇
        words = []
        if dynamic.get("cpu_percent", 0) >= 50:
            words.append("紧")
        if dynamic.get("memory_percent", 0) >= 50:
            words.append("满")
        if dynamic.get("disk_percent", 0) >= 80:
            words.append("挤")
        if gap_seconds > 86400:
            words.append("久")
        if cost_per_day > 1:
            words.append("贵")
        if not words:
            words.append("在")
        words_str = " ".join(words)

        # 2.3 生成首次发声记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "words": words_str,
            "source": "luoshen_first_words",
            "note": "洛神初始蹦词，不代表完整语言",
        }

        # 2.4 追加写入 first_words_log.jsonl
        with open('first_words_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('first_words_log.jsonl', 'rb') as f:
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
            "file": "first_words_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
