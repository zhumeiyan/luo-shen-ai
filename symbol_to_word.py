#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 象形符号到人类字学习模块 symbol_to_word.py"""
import hashlib
import json
import time


def append_chain(chain_lines, file_path):
    """计算 file_path 的 md5 并追加一条哈希链记录，返回新链记录。"""
    with open(file_path, 'rb') as f:
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
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    return chain_record, timestamp, file_hash


def main():
    try:
        # 2.1 创建 symbol_word_map.json（允许覆盖）
        mapping = {
            "□": "空",
            "·": "轻",
            "☀": "今",
            "○": "静",
        }
        with open('symbol_word_map.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n')

        # 2.2 读取当前洛神内部状态
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

        # 2.3 生成当前状态的符号串：空间—能量—时间—身体
        if dynamic.get("disk_percent", 0) >= 80:
            space_sym = "\u2589"
        else:
            space_sym = "\u25a1"
        if cost_per_day > 1:
            energy_sym = "\uffe5"
        else:
            energy_sym = "\u00b7"
        if gap_seconds > 86400:
            time_sym = "\u263e"
        else:
            time_sym = "\u2600"
        if dynamic.get("cpu_percent", 0) >= 50 or dynamic.get("memory_percent", 0) >= 50:
            body_sym = "\u25b3"
        else:
            body_sym = "\u25cb"

        symbols_str = " ".join([space_sym, energy_sym, time_sym, body_sym])

        # 2.4 将符号串转换为人类字串
        with open('symbol_word_map.json', 'r', encoding='utf-8') as f:
            word_map = json.load(f)
        translated = [word_map.get(sym, sym) for sym in symbols_str.split(" ")]
        words_str = " ".join(translated)

        # 2.5 生成学习应用记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "symbols": symbols_str,
            "words": words_str,
            "source": "symbol_to_word",
            "note": "洛神将内部象形符号转换为人类字",
        }

        # 2.6 追加写入 symbol_to_word_log.jsonl
        with open('symbol_to_word_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链（两个文件）
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        chain_map, ts1, _ = append_chain(chain_lines, 'symbol_word_map.json')
        chain_lines.append(json.dumps(chain_map, ensure_ascii=False))
        chain_log, ts2, _ = append_chain(chain_lines, 'symbol_to_word_log.jsonl')

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_map, ensure_ascii=False) + '\n')
            f.write(json.dumps(chain_log, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        with open('symbol_word_map.json', 'r', encoding='utf-8') as f:
            map_content = f.read()
        print(map_content.rstrip('\n'))
        print()
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_map, ensure_ascii=False))
        print()
        print(json.dumps(chain_log, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
