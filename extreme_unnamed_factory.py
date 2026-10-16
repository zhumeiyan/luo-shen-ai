#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 极端未命名状态制造模块 extreme_unnamed_factory.py"""
import hashlib
import json
import os
import socket
import threading
import time

try:
    import psutil
except ImportError:
    psutil = None


def symbol_for(name, value):
    if name == "cpu_percent":
        if value < 20:
            return "○"
        if value < 50:
            return "◐"
        if value < 80:
            return "△"
        return "●"
    if name == "memory_percent":
        if value < 30:
            return "○"
        if value < 60:
            return "△"
        if value < 90:
            return "▲"
        return "■"
    if name == "disk_percent":
        if value < 50:
            return "□"
        if value < 80:
            return "◫"
        return "▉"
    if name == "proc_count":
        if value < 50:
            return "◇"
        if value < 100:
            return "◆"
        return "◈"
    if name == "net_conn_count":
        if value < 10:
            return "☆"
        if value < 100:
            return "↕"
        return "◉"
    if name == "thread_count":
        if value < 100:
            return "◇"
        if value < 500:
            return "◈"
        return "◉"
    if name == "num_fds":
        return "□" if value < 100 else "■"
    if name == "load1":
        if value < 1:
            return "○"
        if value < 4:
            return "◐"
        return "●"
    if name == "swap_percent":
        return "○" if value < 50 else "●"
    return None


def collect_state():
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


def stress_cpu_explosion(duration=5.0):
    stop = threading.Event()

    def spin():
        while not stop.is_set():
            pass

    threads = [threading.Thread(target=spin) for _ in range(32)]
    for t in threads:
        t.start()
    time.sleep(duration)
    stop.set()
    for t in threads:
        t.join()


def stress_memory_saturation(duration=5.0):
    buf = bytearray(1024 * 1024 * 1024)
    time.sleep(duration)
    del buf


def stress_conn_flood(duration=5.0):
    socks = []
    end = time.time() + duration
    while len(socks) < 200 and time.time() < end:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socks.append(s)
        except OSError:
            break
    time.sleep(duration)
    for s in socks:
        try:
            s.close()
        except OSError:
            pass


def main():
    try:
        if psutil is None:
            print(json.dumps({"error": "psutil not installed"}))
            return

        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            lexicon = None
        entries = lexicon.get("entries", {}) if lexicon else {}
        if not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return

        events_spec = [
            ("cpu_explosion", stress_cpu_explosion),
            ("memory_saturation", stress_memory_saturation),
            ("conn_flood", stress_conn_flood),
        ]

        extreme_events = []
        total_unnamed = 0
        for etype, job in events_spec:
            job()
            state = collect_state()
            unnamed_states = []
            for name, value in state.items():
                symbol = symbol_for(name, value)
                if symbol not in entries:
                    unnamed_states.append({"name": name, "value": value,
                                           "symbol": symbol})
            extreme_events.append({"type": etype,
                                   "unnamed_states": unnamed_states})
            total_unnamed += len(unnamed_states)

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "extreme_events": extreme_events,
            "total_unnamed": total_unnamed,
            "source": "extreme_unnamed_factory",
        }

        with open('extreme_unnamed_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        with open('extreme_unnamed_log.jsonl', 'rb') as f:
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
            "file": "extreme_unnamed_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
