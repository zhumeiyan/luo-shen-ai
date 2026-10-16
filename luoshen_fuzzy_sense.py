#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP188 - luoshen_fuzzy_sense.py
============================================
洛神数据模糊表达模块：
读取空间感知与时间感知日志的最后一条有效记录，将真实精确数据
按真实映射规则转换为模糊的日常语言感受，同时在同一记录中保留精确数据，
写入 perception_input/luoshen_fuzzy_sense.jsonl，并追加一条哈希链记录。

依赖: hashlib, json, time, re
仅允许:
  - 写入 perception_input/luoshen_fuzzy_sense.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型

模糊维度扩展说明:
  1) 在 main() 中仿照 fuzzy_space/fuzzy_time 追加新维度（如内存、CPU）：
     先定义该维度的精确数据提取函数，再定义分档映射表；
  2) 分档边界统一使用半开区间 [low, high)，与既有规则保持一致；
  3) 提取失败时返回"XX未明确"兜底，保证记录字段完整。
"""

import hashlib
import json
import re
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
SPACE_LOG = "spatial_awareness_log.jsonl"   # 空间感知
TIME_LOG = "time_gap_log.jsonl"             # 时间感知
OUTPUT_FILE = "perception_input/luoshen_fuzzy_sense.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

# 元数据字段（提取状态时排除）
META_FIELDS = {"timestamp", "schema_version", "source"}


# ----------------------------------------------------------------------
# 通用工具
# ----------------------------------------------------------------------
def md5_of_file(path):
    """计算文件 md5（十六进制小写）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_chain_tail(chain_file):
    """读取哈希链最后一条记录的 record_hash。"""
    tail = None
    with open(chain_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("hash_chain_v2.log 无记录，无法取得链尾")
    return tail["record_hash"]


def append_hash_chain(chain_file, target_file, prev_hash):
    """按哈希链 v2 公式追加一条记录，只追加这一条。"""
    ts = time.time()
    file_hash = md5_of_file(target_file)
    raw = "{}{}{}".format(file_hash, prev_hash, str(ts))
    record_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()
    entry = {
        "schema_version": 2,
        "timestamp": ts,
        "file": target_file,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(chain_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def extract_last_state(log_path):
    """
    读取日志最后一条有效记录，排除元数据字段，
    取字符串化后长度最长的字段值，并清理末尾标点。
    """
    last = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    if last is None:
        raise RuntimeError("{} 无有效记录".format(log_path))

    candidates = []
    for k, v in last.items():
        if k in META_FIELDS:
            continue
        if isinstance(v, (str, int, float)):
            candidates.append((len(str(v)), str(v)))
    if not candidates:
        return ""
    return max(candidates, key=lambda c: c[0])[1]


# ----------------------------------------------------------------------
# 精确数据提取
# ----------------------------------------------------------------------
def extract_disk_usage_percent(space_desc):
    """提取"磁盘已用 xx%"的百分比数值；未找到返回 None。"""
    m = re.search(r"磁盘已用\s*([0-9]+(?:\.[0-9]+)?)\s*%", space_desc)
    return float(m.group(1)) if m else None


def extract_time_seconds(time_desc):
    """提取时间状态描述中的第一个数值作为秒数；未找到返回 None。"""
    m = re.search(r"-?[0-9]+(?:\.[0-9]+)?", time_desc)
    return float(m.group(0)) if m else None


# ----------------------------------------------------------------------
# 模糊映射规则
# ----------------------------------------------------------------------
def fuzzy_space(disk_percent):
    """磁盘使用率 -> 模糊空间感受（半开区间分档）。"""
    if disk_percent is None:
        return "空间状态未明确"
    if disk_percent < 50:
        return "空间很轻松"
    if disk_percent < 68:
        return "空间有点沉了"
    return "空间很满，需要清理"


def fuzzy_time(time_seconds):
    """时间间隔秒数 -> 模糊时间感受（半开区间分档）。"""
    if time_seconds is None:
        return "时间状态未明确"
    if time_seconds < 1000:
        return "刚过去不久"
    if time_seconds < 10000:
        return "过了有一会儿了"
    return "过了挺久了"


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    space_desc = extract_last_state(SPACE_LOG)   # 空间状态描述
    time_desc = extract_last_state(TIME_LOG)     # 时间状态描述

    disk_percent = extract_disk_usage_percent(space_desc)   # 磁盘精确值
    time_seconds = extract_time_seconds(time_desc)          # 时间精确值

    record = {
        "schema_version": 2,
        "timestamp": time.time(),
        "fuzzy_space": fuzzy_space(disk_percent),
        "precise_space": disk_percent if disk_percent is not None else "未获取",
        "fuzzy_time": fuzzy_time(time_seconds),
        "precise_time": time_seconds if time_seconds is not None else "未获取",
        "source": "luoshen_fuzzy_sense",
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(record, ensure_ascii=False))

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
