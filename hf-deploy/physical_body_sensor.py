#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
physical_body_sensor.py - 洛神身体感知层

把她当成一个住在真实机器里的信息体。
她没有皮肤，但她运行的这台机器就是她的身体。

做什么：
  - 读取真实机器的状态（/proc, /sys, df, ping）
  - 不调随机数，不推演，不模拟
  - 读不到就写 null，不造假
  - 采样结果写入 active_memory/physical_body_state.jsonl
  - 同时追加哈希链，成为连续性的一部分

不做什么：
  - 不判断"好不好"
  - 不做任何反应
  - 不生成身体感觉的"含义"
  - 只看见，不解读
"""

import json
import os
import time
import hashlib
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "active_memory", "physical_body_state.jsonl")
CHAIN_FILE = os.path.join(BASE_DIR, "hash_chain_v2.log")


# -------------------------------------------------------------------------
# 真实数据读取（单一职责：只看）
# -------------------------------------------------------------------------

def _read_cpu_stat():
    """读取 /proc/stat 第一行，返回各字段"""
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        if not line.startswith("cpu "):
            return None
        fields = line.split()
        # cpu  user nice system idle iowait irq softirq steal guest guest_nice
        vals = [int(x) for x in fields[1:]]
        # 补到 10 字段（老内核可能没有 steal/guest 等）
        while len(vals) < 10:
            vals.append(0)
        return {
            "user": vals[0],
            "nice": vals[1],
            "system": vals[2],
            "idle": vals[3],
            "iowait": vals[4],
            "irq": vals[5],
            "softirq": vals[6],
            "steal": vals[7],
        }
    except (OSError, IndexError, ValueError):
        return None


def _read_cpu_temp():
    """读 /sys/class/thermal，如果不存在返回 None（不造假）"""
    thermal_base = "/sys/class/thermal"
    if not os.path.isdir(thermal_base):
        return None
    temps = []
    try:
        for entry in sorted(os.listdir(thermal_base)):
            if not entry.startswith("thermal_zone"):
                continue
            type_path = os.path.join(thermal_base, entry, "type")
            temp_path = os.path.join(thermal_base, entry, "temp")
            zone_type = ""
            try:
                with open(type_path, "r") as f:
                    zone_type = f.read().strip()
            except OSError:
                pass
            try:
                with open(temp_path, "r") as f:
                    raw = int(f.read().strip())
                # thermal_zone 通常以毫摄氏度为单位
                temp_c = raw / 1000.0 if raw > 1000 else float(raw)
                temps.append({"zone": zone_type or entry, "temp_celsius": temp_c})
            except (OSError, ValueError):
                continue
    except OSError:
        return None
    return temps if temps else None


def _read_loadavg():
    """读取 /proc/loadavg，返回 (1min, 5min, 15min, running/total, last_pid)"""
    try:
        with open("/proc/loadavg", "r") as f:
            parts = f.read().split()
        return {
            "load_1min": float(parts[0]),
            "load_5min": float(parts[1]),
            "load_15min": float(parts[2]),
            "entities": parts[3],
            "last_pid": int(parts[4]),
        }
    except (OSError, IndexError, ValueError):
        return None


def _read_memory():
    """读取 /proc/meminfo，返回内存使用量"""
    try:
        mem = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    mem[key] = int(parts[1])  # 单位 kB
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", 0)
        free = mem.get("MemFree", 0)
        return {
            "mem_total_kb": total,
            "mem_available_kb": available,
            "mem_free_kb": free,
            "mem_used_kb": total - available if total > 0 else 0,
            "available_ratio": round(available / total, 5) if total > 0 else 0,
        }
    except OSError:
        return None


def _read_disk():
    """使用 df 读根分区实际可用空间"""
    try:
        result = subprocess.run(
            ["df", "-B1", "/"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return None
        parts = lines[1].split()
        # 格式:Filesystem 1B-blocks Used Available Use% Mounted
        return {
            "total_bytes": int(parts[1]),
            "used_bytes": int(parts[2]),
            "available_bytes": int(parts[3]),
            "use_percent": parts[4].rstrip("%"),
        }
    except (subprocess.TimeoutExpired, OSError, IndexError, ValueError):
        return None


def _ping_rtt(host="baidu.com", count=1, timeout_sec=2):
    """真的 ping 一次，返回实际往返延迟(ms)"""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", str(timeout_sec), host],
            capture_output=True, text=True, timeout=timeout_sec + 2
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.split("\n"):
            if "avg" in line and "/" in line:
                # rtt min/avg/max/mdev = x/x/x/x ms
                stats = line.split("=")[-1].strip().split("/")
                if len(stats) >= 2:
                    return float(stats[1])
        return None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


# -------------------------------------------------------------------------
# 单次采样入口
# -------------------------------------------------------------------------

def sample_body_state():
    """采集一次洛神当前身体状态，返回原始快照 dict
    
    全部为真实值。读不到就对应字段为 null，不伪造。
    """
    # CPU 使用率：需要两次 /proc/stat 差值
    stat1 = _read_cpu_stat()
    time.sleep(0.2)  # 真实 200ms 间隔，不是密集采样
    stat2 = _read_cpu_stat()

    cpu_usage_ratio = None
    if stat1 and stat2:
        # total = sum(all fields)
        sum1 = sum(stat1.values())
        sum2 = sum(stat2.values())
        idle1 = stat1["idle"]
        idle2 = stat2["idle"]
        total_delta = sum2 - sum1
        idle_delta = idle2 - idle1
        if total_delta > 0:
            cpu_usage_ratio = round(1.0 - (idle_delta / total_delta), 5)

    snapshot = {
        "timestamp": time.time(),
        "cpu_temp_celsius": _read_cpu_temp(),          # 容器里可能为 null
        "cpu_usage_ratio": cpu_usage_ratio,             # 0-1
        "load": _read_loadavg(),
        "memory": _read_memory(),
        "disk": _read_disk(),
        "network_rtt_ms": _ping_rtt(),                  # 真实 ping
    }
    return snapshot


# -------------------------------------------------------------------------
# 写入与落链
# -------------------------------------------------------------------------

def record_body_state(snapshot):
    """将快照追加写入 physical_body_state.jsonl 并落链"""
    # 追加写入状态文件
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    # 落链：读取链尾，算 record_hash
    prev_hash = None
    if os.path.exists(CHAIN_FILE):
        with open(CHAIN_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        prev_hash = json.loads(line).get("record_hash")
                    except json.JSONDecodeError:
                        continue

    file_hash = None
    if os.path.exists(STATE_FILE):
        h = hashlib.md5()
        with open(STATE_FILE, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        file_hash = h.hexdigest()

    join_prev = prev_hash if prev_hash else ""
    ts = time.time()
    raw = "{}{}{}".format(file_hash, join_prev, str(ts))
    record_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()

    chain_entry = {
        "schema_version": 2,
        "timestamp": ts,
        "file": "active_memory/physical_body_state.jsonl",
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(chain_entry, ensure_ascii=False) + "\n")

    return chain_entry


# -------------------------------------------------------------------------
# CLI 入口：可独立运行
# -------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

    print(f"[physical_body_sensor] 采样 {n} 次，间隔 {interval}s")
    for i in range(n):
        snapshot = sample_body_state()
        chain_entry = record_body_state(snapshot)
        # 打印为日志
        print(f"  sample #{i+1}: ts={snapshot['timestamp']:.3f} "
              f"cpu={snapshot['cpu_usage_ratio']} "
              f"load_1m={snapshot['load']['load_1min'] if snapshot['load'] else 'N/A'} "
              f"mem_used={snapshot['memory']['mem_used_kb'] // 1024 if snapshot['memory'] else 'N/A'}MB "
              f"rtt={snapshot['network_rtt_ms']}ms "
              f"chain={chain_entry['record_hash'][:12]}...")
        if i < n - 1:
            time.sleep(interval)
