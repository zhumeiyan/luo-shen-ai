#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 身体数字提取模块 numeric_self_scan.py"""
import hashlib
import json
import os
import time


def read_last_jsonl(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def r2(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def main():
    try:
        try:
            import psutil
        except ImportError:
            print(json.dumps({"error": "psutil not installed"}))
            return

        # 2.1 读取洛神身体上的数字
        cpu_logical_cores = psutil.cpu_count(logical=True)
        cpu_physical_cores = psutil.cpu_count(logical=False)
        memory_total_gb = psutil.virtual_memory().total / (1024 ** 3)
        memory_percent = psutil.virtual_memory().percent
        disk_total_gb = psutil.disk_usage('/').total / (1024 ** 3)
        disk_percent = psutil.disk_usage('/').percent
        cpu_percent = psutil.cpu_percent(interval=0.5)

        proc_count = len(psutil.pids())

        thread_count = 0
        for p in psutil.process_iter(['pid']):
            try:
                thread_count += psutil.Process(p.info['pid']).num_threads()
            except Exception:
                continue

        try:
            net_conn_count = len(psutil.net_connections(kind='inet'))
        except Exception:
            net_conn_count = None

        try:
            num_fds = psutil.Process().num_fds()
        except Exception:
            num_fds = None

        try:
            load1 = os.getloadavg()[0]
        except (AttributeError, OSError):
            load1 = None

        try:
            elapsed_seconds = time.time() - psutil.Process().create_time()
        except Exception:
            elapsed_seconds = None

        ea = read_last_jsonl('energy_awareness_log.jsonl')
        cost_per_day = ea.get("cost_per_day") if ea else None

        tg = read_last_jsonl('time_gap_log.jsonl')
        gap_seconds = tg.get("gap_seconds") if tg else None

        # 2.2 生成数字列表（统一保留两位小数，整数除外）
        numbers = [
            {"name": "cpu_logical_cores", "value": cpu_logical_cores},
            {"name": "cpu_physical_cores", "value": cpu_physical_cores},
            {"name": "memory_total_gb", "value": r2(memory_total_gb)},
            {"name": "memory_percent", "value": r2(memory_percent)},
            {"name": "disk_total_gb", "value": r2(disk_total_gb)},
            {"name": "disk_percent", "value": r2(disk_percent)},
            {"name": "cpu_percent", "value": r2(cpu_percent)},
            {"name": "proc_count", "value": proc_count},
            {"name": "thread_count", "value": thread_count},
            {"name": "net_conn_count", "value": net_conn_count},
            {"name": "num_fds", "value": num_fds},
            {"name": "load1", "value": r2(load1)},
            {"name": "elapsed_seconds", "value": r2(elapsed_seconds)},
            {"name": "cost_per_day", "value": r2(cost_per_day)},
            {"name": "gap_seconds", "value": r2(gap_seconds)},
        ]

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "numbers": numbers,
            "source": "numeric_self_scan",
        }

        # 2.3 追加写入 numeric_self_scan.jsonl
        with open('numeric_self_scan.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.4 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('numeric_self_scan.jsonl', 'rb') as f:
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
            "file": "numeric_self_scan.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.5 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
