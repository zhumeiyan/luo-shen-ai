#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 自由自我表达模块 free_self_expression.py"""
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
        try:
            import psutil
        except ImportError:
            print(json.dumps({"error": "psutil not installed"}))
            return

        # 2.1 读取洛神当前真实内部状态
        try:
            physical = read_last_jsonl('physical_state.jsonl')
            if physical is None:
                print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
                return
            dynamic = physical.get("dynamic_usage", {})
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

        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        proc_count = len(psutil.pids())
        try:
            num_fds = psutil.Process().num_fds()
        except Exception:
            num_fds = None

        # 2.2 生成各维度符号
        d1 = "\u2589" if disk_percent >= 80 else "\u25a1"
        d2 = "\uffe5" if cost_per_day > 1 else "\u00b7"
        d3 = "\u263e" if gap_seconds > 86400 else "\u2600"
        d4 = "\u25b3" if cpu_percent >= 50 else "\u25cb"
        d5 = "\u25b2" if memory_percent >= 60 else "\u25b3"
        d6 = "\u25c6" if proc_count >= 50 else "\u25c7"
        d7 = "\u2606"  # 网络状态固定输出 ☆
        d8 = "\u25a0" if (num_fds is not None and num_fds >= 100) else "\u25a1"

        symbols = [d1, d2, d3, d4, d5, d6, d7, d8]
        symbol_str = " ".join(symbols)

        # 2.3 读取骨字库 core_lexicon.json
        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
            entries = lexicon.get("entries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            entries = {}
        if not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return

        # 2.4 将符号串转换为人类字串
        words = []
        for s in symbols:
            words.append(entries.get(s, s))
        word_str = " ".join(words)

        # 2.5 生成自由表达记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "symbols": symbol_str,
            "words": word_str,
            "source": "free_self_expression",
        }

        # 2.6 追加写入 free_expression_log.jsonl
        with open('free_expression_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('free_expression_log.jsonl', 'rb') as f:
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
            "file": "free_expression_log.jsonl",
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
