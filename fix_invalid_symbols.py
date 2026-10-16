#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 符号合法性修正模块 fix_invalid_symbols.py"""
import hashlib
import json
import time

VALID_SYMBOLS = ["□", "▉", "·", "￥", "☀", "☾", "○", "△", "▲", "◇",
                 "◆", "☆", "↕", "↻", "◐", "◑", "●", "◈", "◉", "■"]

REPLACE_MAP = {
    "☐": "□",
    "★": "☆",
    "↑": "△",
    "▽": "▲",
    "▼": "▲",
    "☇": "☆",
    "☉": "☀",
    "☎": "◇",
}


def fix_symbol(symbol):
    if symbol in VALID_SYMBOLS:
        return symbol
    if symbol in REPLACE_MAP:
        return REPLACE_MAP[symbol]
    return "○"


def main():
    try:
        # 2.1 读取现有 hanzi_symbol_map.json
        try:
            with open('hanzi_symbol_map.json', 'r', encoding='utf-8') as f:
                smap = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            smap = None
        entries = smap.get("entries", {}) if smap else {}
        if not entries:
            print(json.dumps({"error": "hanzi_symbol_map.json empty or not found"}))
            return

        # 2.4 遍历 entries 并修正 symbol 字段
        for char, info in entries.items():
            if isinstance(info, dict) and "symbol" in info:
                info["symbol"] = fix_symbol(info["symbol"])

        # 2.5 写回 hanzi_symbol_map.json
        with open('hanzi_symbol_map.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(smap, ensure_ascii=False, indent=2) + '\n')

        # 2.6 计算 md5
        with open('hanzi_symbol_map.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.7 追加哈希链
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
            "file": "hanzi_symbol_map.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        with open('hanzi_symbol_map.json', 'r', encoding='utf-8') as f:
            print(f.read(), end="")
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
