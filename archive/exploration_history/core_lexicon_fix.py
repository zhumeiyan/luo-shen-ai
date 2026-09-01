#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 骨字库修正模块 core_lexicon_fix.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取 core_lexicon.json
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 2.2 修正网络维度词：☆ 从 "静" 改为 "息"
        if "entries" in data and "\u2606" in data["entries"]:
            data["entries"]["\u2606"] = "\u606f"

        # 2.3 写回 core_lexicon.json
        with open('core_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

        # 2.4 计算 md5
        with open('core_lexicon.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.5 追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        records_chain = [json.loads(ln) for ln in chain_lines]
        prev_hash = records_chain[-1].get("record_hash") if records_chain else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "core_lexicon.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            content = f.read()
        print(content, end='')
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
