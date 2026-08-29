#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 状态波动观察模块 state_fluctuation_watch.py"""
import hashlib
import json
import time

try:
    import psutil
except ImportError:
    psutil = None

import os


def symbol_for(name, value):
    if name == "cpu_percent":
        return "△" if value >= 50 else "○"
    if name == "memory_percent":
        return "▲" if value >= 60 else "△"
    if name == "disk_percent":
        return "▉" if value >= 80 else "□"
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
    return None


def sample_once():
    try:
        load1 = os.getloadavg()[0]
    except (AttributeError, OSError):
        load1 = 0.0
    try:
        num_fds = psutil.Process().num_fds()
    except Exception:
        num_fds = 0.0
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "proc_count": len(psutil.pids()),
        "net_conn_count": len(psutil.net_connections(kind='inet')),
        "thread_count": psutil.Process().num_threads(),
        "num_fds": num_fds,
        "load1": load1,
        "swap_percent": psutil.swap_memory().percent,
    }


def main():
    try:
        if psutil is None:
            print(json.dumps({"error": "psutil not installed"}))
            return

        # 2.1 连续采样5次，每次间隔1秒
        samples = []
        for seq in range(1, 6):
            values = sample_once()
            samples.append({"seq": seq, "time": time.time(), "values": values})
            if seq < 5:
                time.sleep(1)

        # 2.2 计算每个维度的波动性
        dims = ["cpu_percent", "memory_percent", "disk_percent",
                "proc_count", "net_conn_count", "thread_count", "num_fds",
                "load1", "swap_percent"]
        fluctuations = []
        current = {}
        for name in dims:
            vals = [s["values"][name] for s in samples]
            mn = min(vals)
            mx = max(vals)
            rng = mx - mn
            status = "changing" if rng > 0 else "static"
            fluctuations.append({"name": name, "min": mn, "max": mx,
                                 "range": rng, "status": status})
            current[name] = samples[-1]["values"][name]

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

        # 2.4 标记状态
        unnamed_and_changing = []
        unnamed_but_static = []
        for fluc in fluctuations:
            name = fluc["name"]
            symbol = symbol_for(name, current[name])
            if symbol in entries:
                continue
            item = {"name": name, "symbol": symbol, "range": fluc["range"]}
            if fluc["range"] > 0:
                unnamed_and_changing.append(item)
            else:
                unnamed_but_static.append(item)

        # 2.5 生成观察记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "samples": samples,
            "fluctuations": fluctuations,
            "unnamed_and_changing": unnamed_and_changing,
            "unnamed_but_static": unnamed_but_static,
            "source": "state_fluctuation_watch",
        }

        # 2.6 追加写入 state_fluctuation_log.jsonl
        with open('state_fluctuation_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        with open('state_fluctuation_log.jsonl', 'rb') as f:
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
            "file": "state_fluctuation_log.jsonl",
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
