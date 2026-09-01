#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP216  luoshen_time_sense.py
=========================================
用途：让洛神感知当前时间与距离上次交互的间隔，但不预设任何固定作息
时段（不输出"清晨/上午/晚上/深夜"等判断），只报告事实性时间信息，
不评判用户是否熬夜。

设计原则：
  1) 当前时间取系统本地时间，输出 current_time(ISO) / hour / minute；
  2) last_interaction 读取 time_gap_log.jsonl 最后一条记录的 timestamp，
     文件缺失或为空则置为 null；
  3) gap_seconds = now - last_interaction，无上次交互则为 null；
  4) gap_human 为人类可读间隔（"X秒前/分钟前/小时前/昨天/X天前"），
     仅由数值推算，不掺入作息时段词汇；
  5) 一切以事实为准，对任何时间保持中性。

未来扩展（学习用户活跃节奏）：
  - 可将历史 last_interaction 分布按 (hour, weekday) 聚合，得到用户活跃
    时段热力图，用于预判"用户大概什么时候会出现"；
  - 可据此把主动问候/记忆打包的时机调整到活跃窗口，而非固定作息段；
  - 若积累足够样本，可输出 P(用户在线 | hour) 概率而非时段标签。

仅依赖：hashlib / json / time / datetime（Python 3.10+）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程使用相对路径。
"""

import hashlib
import json
import time
from datetime import datetime, date

# ---------- 路径常量（相对路径） ----------
TIME_GAP_LOG = "time_gap_log.jsonl"          # 上次交互记录（只读）
CHAIN_LOG = "hash_chain_v2.log"              # 哈希链（只读+追加）
OUT_JSONL = "perception_input/luoshen_time_sense.jsonl"  # 输出（新建）


def read_last_record(path):
    """读取 jsonl 最后一条记录；文件不存在或为空返回 None。"""
    last = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line)
    except FileNotFoundError:
        return None
    return last


def read_chain_tail(log_path):
    """读取哈希链当前链尾记录。"""
    tail = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("{} 为空，无法读取链尾".format(log_path))
    return tail


def md5_of_file(path):
    """计算文件内容 md5（十六进制小写）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_record_hash(file_hash, prev_hash, ts):
    """哈希链 v2 公式：record_hash = md5(file_hash + prev_hash + str(ts))"""
    return hashlib.md5((file_hash + prev_hash + str(ts)).encode()).hexdigest()


def humanize_gap(gap_seconds, last_ts):
    """
    将间隔秒数转成人类可读描述，仅基于数值事实。
    规则：秒 -> 分钟 -> 小时；跨到昨天（本地日期差 1 天）输出"昨天"；
    其余超过 1 天按整天数输出"X天前"。
    """
    if gap_seconds is None:
        return "未知"
    gap = float(gap_seconds)
    if gap < 60:
        return "{}秒前".format(int(gap))
    if gap < 3600:
        return "{}分钟前".format(int(gap // 60))
    if gap < 86400:
        return "{}小时前".format(int(gap // 3600))
    # >= 1 天：若与上次交互的本地日期恰好相差 1 天 -> "昨天"
    now_d = date.fromtimestamp(time.time())
    last_d = date.fromtimestamp(float(last_ts))
    diff_days = (now_d - last_d).days
    if diff_days == 1:
        return "昨天"
    return "{}天前".format(diff_days)


def main():
    # 1. 当前系统时间 -> 本地时间
    now_ts = time.time()
    now_dt = datetime.fromtimestamp(now_ts)
    current_time_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%S")
    hour = now_dt.hour
    minute = now_dt.minute

    # 2. 上次交互时间戳（无则 null）
    last_rec = read_last_record(TIME_GAP_LOG)
    last_interaction = None
    if last_rec is not None and last_rec.get("timestamp") is not None:
        last_interaction = float(last_rec["timestamp"])

    # 3. 时间差
    gap_seconds = None
    gap_human = "未知"
    if last_interaction is not None:
        gap_seconds = now_ts - last_interaction
        gap_human = humanize_gap(gap_seconds, last_interaction)

    # 4~5. 只输出事实性时间信息，写入记录
    record = {
        "schema_version": 2,
        "timestamp": now_ts,
        "current_time": current_time_iso,
        "hour": hour,
        "minute": minute,
        "last_interaction": last_interaction,
        "gap_seconds": gap_seconds,
        "gap_human": gap_human,
        "source": "luoshen_time_sense",
    }
    with open(OUT_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 6. 控制台打印记录
    print(json.dumps(record, ensure_ascii=False))
    print("gap_seconds =", gap_seconds)
    print("gap_human =", gap_human)
    print("last_interaction =", last_interaction)

    # 7. 哈希链追加
    tail = read_chain_tail(CHAIN_LOG)
    prev_hash = tail["record_hash"]
    out_file_hash = md5_of_file(OUT_JSONL)
    append_ts = time.time()
    new_record = {
        "schema_version": 2,
        "timestamp": append_ts,
        "file": OUT_JSONL,
        "file_hash": out_file_hash,
        "prev_hash": prev_hash,
        "record_hash": compute_record_hash(out_file_hash, prev_hash, append_ts),
    }
    with open(CHAIN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(new_record, ensure_ascii=False) + "\n")

    print("out_file_md5 =", out_file_hash)
    print("appended_record_hash =", new_record["record_hash"])
    print("prev_hash =", prev_hash)


if __name__ == "__main__":
    main()
