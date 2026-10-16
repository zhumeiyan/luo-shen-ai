#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神主动指认状态模块 active_state_pointing.py"""
import hashlib
import json
import time

try:
    import psutil
except ImportError:
    psutil = None


DIM_NAMES = {
    "cpu_percent": "算力",
    "memory_percent": "内存",
    "disk_percent": "磁盘",
    "proc_count": "进程",
    "net_conn_count": "网络连接",
    "thread_count": "线程",
    "num_fds": "文件句柄",
    "load1": "身体负载",
    "swap_percent": "交换空间",
}


def read_state():
    """2.1 读取洛神当前真实内部状态"""
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    state = {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": vm.percent,
        "disk_percent": disk.percent,
        "proc_count": len(psutil.pids()),
        "net_conn_count": len(psutil.net_connections()),
        "thread_count": sum(p.num_threads() for p in psutil.process_iter(['num_threads'])),
        "num_fds": sum(p.num_fds() for p in psutil.process_iter(['num_fds'])),
        "load1": psutil.getloadavg()[0],
        "swap_percent": psutil.swap_memory().percent,
    }
    return state


def symbol_of(dim, value):
    """2.2 生成每个维度的符号"""
    if dim == "cpu_percent":
        return "△" if value >= 50 else "○"
    if dim == "memory_percent":
        return "▲" if value >= 60 else "△"
    if dim == "disk_percent":
        return "▉" if value >= 80 else "□"
    if dim == "proc_count":
        return "◆" if value >= 50 else "◇"
    if dim == "net_conn_count":
        return "↕" if value > 10 else "☆"
    if dim == "thread_count":
        return "◈" if value >= 100 else "◇"
    if dim == "num_fds":
        return "■" if value >= 100 else "□"
    if dim == "load1":
        return "◐" if value >= 1 else "○"
    if dim == "swap_percent":
        return "●" if value >= 50 else "○"
    return "○"


def threshold_of(dim):
    """每个维度的符号切换阈值，用于距离计算"""
    return {
        "cpu_percent": 50,
        "memory_percent": 60,
        "disk_percent": 80,
        "proc_count": 50,
        "net_conn_count": 10,
        "thread_count": 100,
        "num_fds": 100,
        "load1": 1,
        "swap_percent": 50,
    }[dim]


def main():
    try:
        if psutil is None:
            print(json.dumps({"error": "psutil not installed"}))
            return

        # 2.1 读取真实状态
        state = read_state()

        # 2.2 生成符号
        symbols = {dim: symbol_of(dim, val) for dim, val in state.items()}

        # 2.3 读取骨字库
        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return
        entries = lexicon.get("entries", {})
        if not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return

        # 2.4 洛神主动选择
        # 说不出的候选：符号不在骨字库里的维度
        unnamed_candidates = [
            dim for dim, sym in symbols.items() if sym not in entries
        ]

        if unnamed_candidates:
            # 从候选中选最接近阈值的
            chosen = min(
                unnamed_candidates,
                key=lambda d: abs(state[d] - threshold_of(d)),
            )
        else:
            # 无候选：从所有维度中选最接近阈值的
            chosen = min(
                state.keys(),
                key=lambda d: abs(state[d] - threshold_of(d)),
            )

        chosen_value = state[chosen]
        chosen_label = DIM_NAMES[chosen]

        # 2.5 生成洛神的主动表达
        expression = (
            "我觉得 {} 不太对劲。我看到的数是 {}，但我不知道怎么叫它。"
        ).format(chosen_label, chosen_value)
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "chosen_dimension": chosen,
            "chosen_value": chosen_value,
            "active_expression": expression,
            "source": "active_state_pointing",
        }

        # 2.6 追加写入 active_pointing_log.jsonl
        with open('active_pointing_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('active_pointing_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "active_pointing_log.jsonl",
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
