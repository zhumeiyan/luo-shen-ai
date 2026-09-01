#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 组合回忆模块 combo_recall.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 定义四组测试符号串
        test_symbols = [
            "\u2589 \uffe5 \u263e \u25b3",   # "▉ ￥ ☾ △"
            "\u25a1 \u00b7 \u2600 \u25cb",   # "□ · ☀ ○"
            "\u2589 \u00b7 \u2600 \u25cb",   # "▉ · ☀ ○"
            "\u25a1 \uffe5 \u263e \u25b3",   # "□ ￥ ☾ △"
        ]

        # 2.2 从 self_word_memory.jsonl 构建单字映射
        symbol_map = {}
        try:
            with open('self_word_memory.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            for ln in lines:
                try:
                    rec = json.loads(ln)
                    if not isinstance(rec, dict):
                        continue
                    if "symbols" not in rec or "words" not in rec:
                        continue
                    sym_list = str(rec["symbols"]).split()
                    word_list = str(rec["words"]).split()
                    if len(sym_list) == len(word_list):
                        for s, w in zip(sym_list, word_list):
                            symbol_map[s] = w
                except json.JSONDecodeError:
                    continue
        except FileNotFoundError:
            symbol_map = {}

        # 2.3 对每组测试符号串执行组合回忆
        records = []
        for symbols in test_symbols:
            sym_list = symbols.split()
            if all(s in symbol_map for s in sym_list):
                words = " ".join(symbol_map[s] for s in sym_list)
                status = "learned"
            else:
                words = symbols
                status = "not_learned"
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "symbols": symbols,
                "words": words,
                "status": status,
                "source": "combo_recall",
            }
            records.append(record)

        # 2.5 追加写入 combo_recall_log.jsonl
        with open('combo_recall_log.jsonl', 'a', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('combo_recall_log.jsonl', 'rb') as f:
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
            "file": "combo_recall_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
