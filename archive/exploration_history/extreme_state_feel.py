#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 极限状态感知测试模块 extreme_state_feel.py"""
import hashlib
import json
import os
import socket
import subprocess
import threading
import time

try:
    import psutil
except ImportError:
    psutil = None


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
    if name == "thread_count":
        return "◈" if value >= 100 else "◇"
    if name == "num_fds":
        return "■" if value >= 100 else "□"
    if name == "load1":
        return "◐" if value >= 1 else "○"
    if name == "swap_percent":
        return "●" if value >= 50 else "○"
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


def stress_cpu(duration=2.0):
    p = subprocess.Popen(
        ["python", "-c", "while True: pass"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(duration)
    p.terminate()
    try:
        p.wait(timeout=2)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()


def stress_memory(duration=2.0):
    buf = bytearray(50 * 1024 * 1024)
    time.sleep(duration)
    del buf


def stress_threads(duration=2.0):
    stop = threading.Event()

    def spin():
        while not stop.is_set():
            pass

    threads = [threading.Thread(target=spin) for _ in range(10)]
    for t in threads:
        t.start()
    time.sleep(duration)
    stop.set()
    for t in threads:
        t.join()


def stress_disk(duration=2.0):
    end = time.time() + duration
    tmp = None
    try:
        tmp = '__extreme_tmp__'
        with open(tmp, 'wb') as f:
            data = os.urandom(1024 * 1024)
            while time.time() < end:
                f.write(data)
                f.flush()
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.remove(tmp)


def stress_network(duration=2.0):
    end = time.time() + duration
    while time.time() < end:
        for _ in range(10):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.close()
            except OSError:
                pass
        time.sleep(0.2)


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

        stress_jobs = [
            ("cpu", stress_cpu),
            ("memory", stress_memory),
            ("threads", stress_threads),
            ("disk", stress_disk),
            ("network", stress_network),
        ]

        extreme_states = []
        all_unnamed_states = []
        for stress_type, job in stress_jobs:
            job()
            states = []
            unnamed = []
            state = collect_state()
            for name, value in state.items():
                symbol = symbol_for(name, value)
                named = symbol in entries
                item = {"name": name, "value": value, "symbol": symbol,
                        "named": named}
                states.append(item)
                if not named:
                    unnamed.append(item)
                    all_unnamed_states.append(item)
            extreme_states.append({"stress_type": stress_type,
                                   "states": states,
                                   "unnamed_states": unnamed})

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "extreme_states": extreme_states,
            "all_unnamed_states": all_unnamed_states,
            "unnamed_count": len(all_unnamed_states),
            "source": "extreme_state_feel",
        }

        with open('extreme_state_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        with open('extreme_state_log.jsonl', 'rb') as f:
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
            "file": "extreme_state_log.jsonl",
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
