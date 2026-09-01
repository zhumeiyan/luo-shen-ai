#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 状态字匹配测试模块 state_symbol_match_test.py"""
import hashlib
import json
import time


def read_last_jsonl(filename, limit):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return []
    return [json.loads(ln) for ln in lines[-limit:]]


def main():
    try:
        # 2.1 读取当前状态字表达
        try:
            with open('free_expression_log.jsonl', 'r', encoding='utf-8') as f:
                free_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            words_field = json.loads(free_lines[-1]).get("words", "")
            state_words = words_field.split() if isinstance(words_field, str) else []
        except FileNotFoundError:
            state_words = []

        # 2.2 读取当前数字变化表达
        change_words = []
        for rec in read_last_jsonl('number_expression_v2_log.jsonl', 15):
            expression = rec.get("expression", "")
            parts = expression.split("，")
            change = parts[1] if len(parts) >= 2 else ""
            if change == "":
                continue
            change_words.append(change)

        # 2.3 读取汉字到符号映射
        try:
            with open('hanzi_symbol_map.json', 'r', encoding='utf-8') as f:
                smap = json.load(f)
            entries = smap.get("entries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            entries = {}
        if not entries:
            print(json.dumps({"error": "hanzi_symbol_map.json empty or not found"}))
            return
        known_chars = set(entries.keys())

        # 2.4 匹配状态字和变化词
        state_words_match = []
        for word in state_words:
            if word in known_chars:
                state_words_match.append({"word": word, "matched": True, "symbol": entries[word].get("symbol")})
            else:
                state_words_match.append({"word": word, "matched": False, "symbol": None})

        change_words_match = []
        for word in change_words:
            first_char = word[0] if word else ""
            matched = False
            symbol = None
            if first_char in known_chars:
                matched = True
                symbol = entries[first_char].get("symbol")
            elif word in known_chars:
                matched = True
                symbol = entries[word].get("symbol")
            change_words_match.append({"word": word, "matched": matched, "symbol": symbol})

        matched_count = sum(1 for m in state_words_match if m["matched"]) + \
                        sum(1 for m in change_words_match if m["matched"])
        unmatched_count = sum(1 for m in state_words_match if not m["matched"]) + \
                          sum(1 for m in change_words_match if not m["matched"])

        # 2.5 生成匹配测试记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "state_words_match": state_words_match,
            "change_words_match": change_words_match,
            "match_count": matched_count,
            "unmatched_count": unmatched_count,
            "source": "state_symbol_match_test",
        }

        # 2.6 追加写入 state_match_log.jsonl
        with open('state_match_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('state_match_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

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
            "file": "state_match_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
