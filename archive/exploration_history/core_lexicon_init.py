#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 骨字库初始化模块 core_lexicon_init.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 创建 core_lexicon.json（允许覆盖，初始固化）
        data = {
            "schema_version": 1,
            "module": "core_lexicon",
            "version": 1,
            "description": "洛神骨字库：由设计者朱美岩教学并固化的核心词汇，永不删除，只可追加。",
            "entries": {
                "\u25a1": "空",
                "\u00b7": "轻",
                "\u2600": "今",
                "\u25cb": "静",
                "\u2589": "满",
                "\uffe5": "贵",
                "\u263e": "久",
                "\u25b3": "紧",
                "\u25c7": "闲",
                "\u2606": "静",
            },
            "rule": "骨字库是洛神深层记忆，不参与上下文过期。只有设计者朱美岩可以追加新词或纠正，任何其他角色不得修改或删除。",
        }

        with open('core_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

        # 2.2 计算 md5
        with open('core_lexicon.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.3 追加哈希链
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

        # 2.4 标准输出
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            content = f.read()
        print(content, end='')
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
