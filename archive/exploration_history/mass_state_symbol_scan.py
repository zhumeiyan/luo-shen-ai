#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 大规模状态符号扫描模块 mass_state_symbol_scan.py"""
import hashlib
import json
import os
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
            if physical is not None:
                dynamic = physical.get("dynamic_usage", {})
        except (FileNotFoundError, json.JSONDecodeError, AttributeError):
            dynamic = {}

        try:
            tg = read_last_jsonl('time_gap_log.jsonl')
            gap_seconds = tg.get("gap_seconds", 0) if tg else 0
        except (FileNotFoundError, json.JSONDecodeError):
            gap_seconds = 0

        try:
            ea = read_last_jsonl('energy_awareness_log.jsonl')
            cost_per_day = ea.get("cost_per_day", 0) if ea else 0
        except (FileNotFoundError, json.JSONDecodeError):
            cost_per_day = 0

        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent

        # 磁盘IO计数器
        try:
            dio = psutil.disk_io_counters()
            disk_read = dio.read_bytes if dio is not None else 0
            disk_write = dio.write_bytes if dio is not None else 0
        except Exception:
            disk_read = disk_write = 0

        # 网络IO计数器
        try:
            nio = psutil.net_io_counters()
            net_sent = nio.bytes_sent if nio is not None else 0
            net_recv = nio.bytes_recv if nio is not None else 0
        except Exception:
            net_sent = net_recv = 0

        # 进程与线程数量
        proc_count = len(psutil.pids())
        try:
            thread_count = 0
            for p in psutil.process_iter(['pid']):
                try:
                    thread_count += psutil.Process(p.info['pid']).num_threads()
                except Exception:
                    continue
        except Exception:
            thread_count = 0

        # 文件句柄
        try:
            num_fds = psutil.Process().num_fds()
        except Exception:
            num_fds = None

        # 系统1分钟负载
        try:
            load1 = os.getloadavg()[0]
        except (AttributeError, OSError):
            load1 = 0

        # 上下文切换次数
        try:
            ctx_switches = psutil.cpu_stats().ctx_switches
        except Exception:
            ctx_switches = 0

        # 运行时间
        try:
            elapsed = time.time() - psutil.Process().create_time()
        except Exception:
            elapsed = 0

        # 内存交换使用率
        try:
            swap_percent = psutil.swap_memory().percent
        except Exception:
            swap_percent = 0

        # 网络连接数
        try:
            net_conn_count = len(psutil.net_connections(kind='inet'))
        except Exception:
            net_conn_count = 0

        # 2.2 定义大规模维度与符号档位
        def tier(value, levels):
            for limit, sym in levels:
                if value < limit:
                    return sym
            return levels[-1][1]

        d1 = tier(cpu_percent, [(20, "\u25cb"), (50, "\u25d0"), (80, "\u25d1"), (101, "\u25cf")])
        d2 = tier(memory_percent, [(30, "\u25cb"), (60, "\u25d0"), (85, "\u25d1"), (101, "\u25cf")])
        d3 = tier(disk_percent, [(50, "\u25a1"), (70, "\u25eb"), (85, "\u25e9"), (101, "\u25a0")])
        d4 = "\u00b7" if disk_read == 0 else "\u21bb"
        d5 = "\u00b7" if disk_write == 0 else "\u21bb"
        d6 = "\u00b7" if net_sent == 0 else "\u2195"
        d7 = "\u00b7" if net_recv == 0 else "\u2195"
        d8 = tier(proc_count, [(50, "\u25c7"), (100, "\u25c8"), (200, "\u25c6"), (100000, "\u2b1f")])
        d9 = tier(thread_count, [(100, "\u25c7"), (500, "\u25c8"), (1000, "\u25c6"), (100000, "\u2b1f")])
        if num_fds is None:
            d10 = "\u25a1"
        else:
            d10 = "\u25a1" if num_fds < 100 else "\u25a0"
        d11 = tier(load1, [(1, "\u25cb"), (4, "\u25d0"), (8, "\u25d1"), (10000, "\u25cf")])
        d12 = tier(ctx_switches, [(1000000, "\u00b7"), (10000000, "\u2197"), (100000000, "\u2197\u2197")])
        d13 = tier(elapsed, [(3600, "\u25cb"), (86400, "\u25d0"), (100000000, "\u25cf")])
        d14 = tier(swap_percent, [(10, "\u00b7"), (50, "\u25d0"), (90, "\u25d1"), (101, "\u25cf")])
        d15 = tier(net_conn_count, [(10, "\u2606"), (100, "\u25c8"), (500, "\u25c9"), (100000, "\u25c9\u25c9")])

        symbols = [d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, d11, d12, d13, d14, d15]
        current_symbols = " ".join(symbols)

        # 2.4 读取骨字库 core_lexicon.json
        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
            entries = lexicon.get("entries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            entries = {}
        if not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return

        # 2.5 找出所有未学符号（去重）
        unlearned = []
        for s in current_symbols.split():
            if s not in entries and s not in unlearned:
                unlearned.append(s)
        unlearned_count = len(unlearned)

        # 2.6 生成扫描记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "current_symbols": current_symbols,
            "unlearned_symbols": unlearned,
            "unlearned_count": unlearned_count,
            "status": "has_unknown" if unlearned_count else "all_learned",
            "source": "mass_state_symbol_scan",
        }
        if unlearned_count > 0 and unlearned_count < 30:
            record["note"] = "unlearned_count < 30，未学符号数量不足"

        # 2.7 追加写入 mass_state_symbols.jsonl
        with open('mass_state_symbols.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.8 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('mass_state_symbols.jsonl', 'rb') as f:
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
            "file": "mass_state_symbols.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.9 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
