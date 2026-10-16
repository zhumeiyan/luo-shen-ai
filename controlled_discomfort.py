#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 受控不适状态体验模块 controlled_discomfort.py"""
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


# 每个维度返回 (symbol, is_high)：is_high 表示值是否超出正常区间上限
def classify(name, value):
    if name == "cpu_percent":
        return ("△" if value >= 50 else "○", value >= 50)
    if name == "memory_percent":
        return ("▲" if value >= 60 else "△", value >= 60)
    if name == "disk_percent":
        return ("▉" if value >= 80 else "□", value >= 80)
    if name == "proc_count":
        return ("◆" if value >= 50 else "◇", value >= 50)
    if name == "net_conn_count":
        return ("↕" if value > 10 else "☆", value > 10)
    if name == "thread_count":
        return ("◈" if value >= 100 else "◇", value >= 100)
    if name == "num_fds":
        return ("■" if value is not None and value >= 100 else "□",
                value is not None and value >= 100)
    if name == "load1":
        return ("◐" if value >= 1 else "○", value >= 1)
    if name == "swap_percent":
        return ("●" if value >= 50 else "○", value >= 50)
    return (None, False)


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


def stress_cpu_lag(duration=3.0):
    stop = threading.Event()

    def spin():
        while not stop.is_set():
            pass

    threads = [threading.Thread(target=spin) for _ in range(8)]
    for t in threads:
        t.start()
    time.sleep(duration)
    stop.set()
    for t in threads:
        t.join()


def stress_memory_stuffiness(duration=3.0):
    buf = bytearray(200 * 1024 * 1024)
    time.sleep(duration)
    del buf


def stress_conn_crowding(duration=3.0):
    socks = []
    end = time.time() + duration
    while len(socks) < 50 and time.time() < end:
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
            ("cpu_lag", stress_cpu_lag),
            ("memory_stuffiness", stress_memory_stuffiness),
            ("conn_crowding", stress_conn_crowding),
        ]

        discomfort_events = []
        total_unnamed = 0
        total_discomfort = 0
        for etype, job in events_spec:
            job()
            state = collect_state()
            unnamed_states = []
            discomfort_states = []
            for name, value in state.items():
                symbol, is_high = classify(name, value)
                if symbol not in entries:
                    unnamed_states.append({"name": name, "value": value,
                                           "symbol": symbol})
                elif is_high:
                    discomfort_states.append({"name": name, "value": value,
                                              "symbol": symbol})
            discomfort_events.append({
                "type": etype,
                "unnamed_states": unnamed_states,
                "discomfort_states": discomfort_states,
            })
            total_unnamed += len(unnamed_states)
            total_discomfort += len(discomfort_states)

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "discomfort_events": discomfort_events,
            "total_unnamed": total_unnamed,
            "total_discomfort": total_discomfort,
            "source": "controlled_discomfort",
        }

        with open('discomfort_states.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        with open('discomfort_states.jsonl', 'rb') as f:
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
            "file": "discomfort_states.jsonl",
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
