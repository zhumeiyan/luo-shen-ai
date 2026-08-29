#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 扩展状态未命名清单模块 extended_unnamed_scan.py"""
import hashlib
import json
import os
import time

try:
    import psutil
except ImportError:
    psutil = None


def last_line(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def main():
    try:
        if psutil is None:
            print(json.dumps({"error": "psutil not installed"}))
            return

        # 2.1 读取洛神当前真实内部状态，扫描至少15个维度
        # psutil 实时读取
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        proc_count = len(psutil.pids())
        try:
            net_conn_count = len(psutil.net_connections(kind='inet'))
        except Exception:
            net_conn_count = None
        try:
            num_fds = psutil.Process().num_fds()
        except Exception:
            num_fds = None
        thread_count = psutil.Process().num_threads()
        swap_percent = psutil.swap_memory().percent
        disk_io = psutil.disk_io_counters()
        disk_read_bytes = disk_io.read_bytes if disk_io else 0
        disk_write_bytes = disk_io.write_bytes if disk_io else 0
        net_io = psutil.net_io_counters()
        net_sent_bytes = net_io.bytes_sent if net_io else 0
        net_recv_bytes = net_io.bytes_recv if net_io else 0

        # os 模块读取系统负载
        try:
            load1 = os.getloadavg()[0]
        except (AttributeError, OSError):
            load1 = None

        # physical_state.jsonl 最后一条
        try:
            phys = last_line('physical_state.jsonl')
        except FileNotFoundError:
            phys = None
        if phys is None:
            dynamic = {}
        else:
            dynamic = phys.get("dynamic_usage", {})

        # time_gap_log.jsonl 最后一条
        try:
            time_gap = last_line('time_gap_log.jsonl')
        except FileNotFoundError:
            time_gap = {}
        gap_seconds = time_gap.get("gap_seconds", 0) if time_gap else 0

        # energy_awareness_log.jsonl 最后一条
        try:
            energy = last_line('energy_awareness_log.jsonl')
        except FileNotFoundError:
            energy = {}
        cost_per_day = energy.get("cost_per_day", 0) if energy else 0

        # 2.2 为每个维度生成符号
        def symbol_for(name, value):
            if name == "cpu_percent":
                return "△" if value >= 50 else "○"
            if name == "memory_percent":
                return "▲" if value >= 60 else "△"
            if name == "disk_percent":
                return "▉" if value >= 80 else "□"
            if name == "cost_per_day":
                return "￥" if value > 1 else "·"
            if name == "gap_seconds":
                return "☾" if value > 86400 else "☀"
            if name == "proc_count":
                return "◆" if value >= 50 else "◇"
            if name == "net_conn_count":
                return "↕" if value > 10 else "☆"
            if name == "num_fds":
                return "■" if value is not None and value >= 100 else "□"
            if name == "thread_count":
                return "◈" if value >= 100 else "◇"
            if name == "load1":
                return "◐" if value >= 1 else "○"
            if name == "swap_percent":
                return "●" if value >= 50 else "○"
            if name == "disk_read_bytes":
                return "↻" if value > 0 else "·"
            if name == "disk_write_bytes":
                return "↻" if value > 0 else "·"
            if name == "net_sent_bytes":
                return "↕" if value > 0 else "·"
            if name == "net_recv_bytes":
                return "↕" if value > 0 else "·"
            return None

        raw_items = [
            ("cpu_percent", cpu_percent),
            ("memory_percent", memory_percent),
            ("disk_percent", disk_percent),
            ("cost_per_day", cost_per_day),
            ("gap_seconds", gap_seconds),
            ("proc_count", proc_count),
            ("net_conn_count", net_conn_count),
            ("num_fds", num_fds),
            ("thread_count", thread_count),
            ("load1", load1),
            ("swap_percent", swap_percent),
            ("disk_read_bytes", disk_read_bytes),
            ("disk_write_bytes", disk_write_bytes),
            ("net_sent_bytes", net_sent_bytes),
            ("net_recv_bytes", net_recv_bytes),
        ]

        symbol_list = []
        for name, value in raw_items:
            symbol_list.append(symbol_for(name, value))
        symbol_str = " ".join(symbol_list)

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

        # 2.4 找出未命名状态
        syms = symbol_str.split(" ")
        unnamed = []
        for i, sym in enumerate(syms):
            if sym not in entries:
                unnamed.append({
                    "name": raw_items[i][0],
                    "value": raw_items[i][1],
                    "symbol": sym,
                    "named": False,
                })

        # 2.5 生成扩展未命名状态清单
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "dimension_count": 15,
            "unnamed_states": unnamed,
            "unnamed_count": len(unnamed),
            "source": "extended_unnamed_scan",
        }

        # 2.6 追加写入 extended_unnamed_states.jsonl
        with open('extended_unnamed_states.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        with open('extended_unnamed_states.jsonl', 'rb') as f:
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
            "file": "extended_unnamed_states.jsonl",
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
