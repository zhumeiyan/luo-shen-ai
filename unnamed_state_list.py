#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 未命名状态清单模块 unnamed_state_list.py"""
import hashlib
import json
import time

import psutil


def last_line(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def main():
    try:
        # 2.1 读取洛神当前真实内部状态
        try:
            phys = last_line('physical_state.jsonl')
        except FileNotFoundError:
            phys = None
        if phys is None:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return
        dynamic = phys.get("dynamic_usage", {})

        try:
            time_gap = last_line('time_gap_log.jsonl')
        except FileNotFoundError:
            time_gap = {}
        gap_seconds = time_gap.get("gap_seconds", 0) if time_gap else 0

        try:
            energy = last_line('energy_awareness_log.jsonl')
        except FileNotFoundError:
            energy = {}
        cost_per_day = energy.get("cost_per_day", 0) if energy else 0

        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        proc_count = len(psutil.pids())
        net_conn_count = len(psutil.net_connections(kind='inet'))
        try:
            num_fds = psutil.Process().num_fds()
        except Exception:
            num_fds = None

        # 2.2 构建状态感知条目
        raw_items = [
            ("cpu_percent", cpu_percent),
            ("memory_percent", memory_percent),
            ("disk_percent", disk_percent),
            ("cost_per_day", cost_per_day),
            ("gap_seconds", gap_seconds),
            ("proc_count", proc_count),
            ("net_conn_count", net_conn_count),
            ("num_fds", num_fds),
        ]

        # 2.3 读取骨字库
        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            lexicon = None
        entries = lexicon.get("entries", {}) if lexicon else {}
        if not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return

        # 2.4 标记未命名状态
        states = []
        for name, value in raw_items:
            symbol = None
            if name == "cpu_percent":
                symbol = "△" if value >= 50 else "○"
            elif name == "memory_percent":
                symbol = "▲" if value >= 60 else "△"
            elif name == "disk_percent":
                symbol = "▉" if value >= 80 else "□"
            elif name == "cost_per_day":
                symbol = "￥" if value > 1 else "·"
            elif name == "gap_seconds":
                symbol = "☾" if value > 86400 else "☀"
            elif name == "proc_count":
                symbol = "◆" if value >= 50 else "◇"
            elif name == "net_conn_count":
                symbol = "↕" if value > 10 else "☆"
            elif name == "num_fds":
                if value is not None and value >= 100:
                    symbol = "■"
                else:
                    symbol = "□"

            named = symbol in entries
            named_word = entries[symbol].get("word") if named else None
            states.append({
                "name": name,
                "value": value,
                "symbol": symbol,
                "named": named,
                "named_word": named_word,
            })

        # 2.5 生成未命名状态清单
        unnamed = [s for s in states if not s["named"]]
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "unnamed_states": unnamed,
            "unnamed_count": len(unnamed),
            "source": "unnamed_state_list",
        }

        # 2.6 追加写入 unnamed_states.jsonl
        with open('unnamed_states.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        with open('unnamed_states.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(lines[-1]).get("record_hash") if lines else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "unnamed_states.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
