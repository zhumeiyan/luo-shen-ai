#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 未学状态扫描模块 unknown_state_scan.py"""
import hashlib
import json
import time


def read_last_jsonl(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def main():
    try:
        # 2.1 读取洛神当前真实内部状态
        try:
            physical = read_last_jsonl('physical_state.jsonl')
            if physical is None:
                print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
                return
            dynamic = physical.get("dynamic_usage", {})
            disk_percent = dynamic.get("disk_percent", 0)
            cpu_percent = dynamic.get("cpu_percent", 0)
            memory_percent = dynamic.get("memory_percent", 0)
        except FileNotFoundError:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return

        try:
            tg = read_last_jsonl('time_gap_log.jsonl')
            gap_seconds = tg.get("gap_seconds", 0) if tg else 0
        except FileNotFoundError:
            gap_seconds = 0

        try:
            ea = read_last_jsonl('energy_awareness_log.jsonl')
            cost_per_day = ea.get("cost_per_day", 0) if ea else 0
        except FileNotFoundError:
            cost_per_day = 0

        # 2.2 生成当前状态符号串
        sp = "\u2589" if disk_percent >= 80 else "\u25a1"
        en = "\uffe5" if cost_per_day > 1 else "\u00b7"
        tm = "\u263e" if gap_seconds > 86400 else "\u2600"
        bd = "\u25b3" if (cpu_percent >= 50 or memory_percent >= 50) else "\u25cb"
        current_symbols = sp + " " + en + " " + tm + " " + bd

        # 2.3 读取学习记忆，构建单字映射
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

        # 2.4 找出未学符号
        unlearned = [s for s in current_symbols.split() if s not in symbol_map]

        # 2.5 生成扫描记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "current_symbols": current_symbols,
            "unlearned_symbols": unlearned,
            "status": "has_unknown" if unlearned else "all_learned",
            "source": "unknown_state_scan",
        }

        # 2.6 追加写入 unknown_states.jsonl
        with open('unknown_states.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('unknown_states.jsonl', 'rb') as f:
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
            "file": "unknown_states.jsonl",
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
