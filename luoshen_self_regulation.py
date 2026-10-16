#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP187 - luoshen_self_regulation.py
================================================
洛神自我调节模块：
读取三个内部感知日志的最后一条有效记录，依据简单调节规则判断是否需要调节，
生成一条"调节请求"写入 perception_input/luoshen_regulation_request.jsonl，
并追加一条哈希链记录。

依赖: hashlib, json, time, re
仅允许:
  - 写入 perception_input/luoshen_regulation_request.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型

调节规则扩展说明:
  1) 在 decide_request() 中按优先级追加新规则（顺序即优先级）；
  2) 如需接入真实探针（如 psutil 磁盘/内存采样），可把
     extract_state() 的数据源替换为探针返回的实时字典；
  3) 规则阈值统一抽成常量 DISK_THRESHOLD / TIME_THRESHOLD，便于调整。
"""

import hashlib
import json
import re
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录）
# ----------------------------------------------------------------------
SPACE_LOG = "spatial_awareness_log.jsonl"           # 空间感知
TIME_LOG = "time_gap_log.jsonl"                     # 时间感知
SELF_LOG = "self_describe_two_states.jsonl"         # 自我感知
OUTPUT_FILE = "perception_input/luoshen_regulation_request.jsonl"  # 调节请求输出
CHAIN_FILE = "hash_chain_v2.log"

# 调节规则阈值
DISK_THRESHOLD = 68.0    # 磁盘占用百分比阈值（>= 触发空间压力调节）
TIME_THRESHOLD = 20000.0 # 时间间隔秒数阈值（>= 触发自我确认调节）

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


def clean_state(s):
    """清理状态文本末尾的孤立/重复标点。"""
    return s.rstrip("。！？，,；;.")


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
    return clean_state(max(candidates, key=lambda c: c[0])[1])


# ----------------------------------------------------------------------
# 调节规则
# ----------------------------------------------------------------------
def extract_disk_usage_percent(space_desc):
    """
    从空间状态描述中提取"磁盘已用 xx%"的百分比数值；
    未找到时返回 None。
    """
    m = re.search(r"磁盘已用\s*([0-9]+(?:\.[0-9]+)?)\s*%", space_desc)
    if m:
        return float(m.group(1))
    return None


def decide_request(space_desc, time_desc, self_desc):
    """
    依据优先级、基于真实提取数值判定调节建议：
      1) 空间压力：磁盘已用百分比 >= DISK_THRESHOLD
      2) 时间确认：时间数值 >= TIME_THRESHOLD
      3) 稳定记录：其余情况
    返回文本均由真实数据（磁盘使用率/时间间隔）驱动，不含主观感受表达。
    """
    # 提取真实数值
    disk_percent = extract_disk_usage_percent(space_desc)
    time_val = None
    m = re.search(r"-?[0-9]+(?:\.[0-9]+)?", time_desc)
    if m:
        time_val = float(m.group(0))

    # 规则1：空间压力（磁盘使用率 >= 阈值）
    if disk_percent is not None and disk_percent >= DISK_THRESHOLD:
        return "磁盘使用率{}%，超过阈值68%，建议清理旧日志或记忆缓存。".format(disk_percent)
    # 规则2：时间确认（时间间隔 >= 阈值）
    if time_val is not None and time_val >= TIME_THRESHOLD:
        return "时间间隔{}秒，超过阈值20000秒，建议进行一次自我确认。".format(time_val)
    # 规则3：稳定记录
    return "磁盘使用率{}%，时间间隔{}秒，状态稳定，暂不请求调节。".format(
        disk_percent if disk_percent is not None else "未知",
        time_val if time_val is not None else "未知",
    )


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    space_desc = extract_last_state(SPACE_LOG)   # 空间状态
    time_desc = extract_last_state(TIME_LOG)     # 时间状态
    self_desc = extract_last_state(SELF_LOG)     # 自我状态

    regulation_request = decide_request(space_desc, time_desc, self_desc)

    ts = time.time()
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "regulation_request": regulation_request,
        "source": "luoshen_self_regulation",
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(regulation_request)

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
