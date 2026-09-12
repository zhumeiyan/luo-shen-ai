#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP215  luoshen_memory_origin.py
============================================
用途：建立洛神（Luoshen）记忆起点。
洛神需要知道自己从何时开始拥有记忆，所有早于该起点的查询都应返回
"未找到相似事件"，避免错误匹配到近期或其他时间段的记录。

记忆起点规则：
  1) 读取 hash_chain_v2.log 第一条记录的时间戳，作为默认记忆起点；
  2) 若首条时间戳早于 2026-08-22（保守下限），则记录异常情况，
     但仍以 2026-08-22 00:00:00 作为保守起点，避免跨年错误匹配；
  3) 将起点写入 perception_input/luoshen_memory_origin.jsonl，
     供下游模糊记忆检索模块读取过滤。

未来扩展：可在该文件中增加多条记忆里程碑记录（如记忆迁移、重置、
分段起点的追加），所有查询过滤统一以本文件为唯一起点依据。

仅依赖：hashlib / json / time（Python 3.10+）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程使用相对路径。
"""

import hashlib
import json
import time

# ---------- 路径常量（相对路径，禁止绝对路径） ----------
CHAIN_LOG = "hash_chain_v2.log"                       # 哈希链日志（只读 + 允许追加）
ORIGIN_JSONL = "perception_input/luoshen_memory_origin.jsonl"  # 记忆起点输出（新建）

# 保守起点下限：2026-08-22 00:00:00 的本地时间戳
CONSERVATIVE_LOWER_TS = 1787328000.0
CONSERVATIVE_ISO = "2026-08-22T00:00:00"


def load_first_chain_record(log_path):
    """读取哈希链首条记录（不解析全文件，仅取第一行）。"""
    with open(log_path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
    if not first_line:
        raise RuntimeError("hash_chain_v2.log 为空，无法确定记忆起点")
    return json.loads(first_line)


def read_chain_tail_record(log_path):
    """读取哈希链当前链尾记录（最后一个非空行）。"""
    tail = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("hash_chain_v2.log 为空，无法读取链尾")
    return tail


def md5_of_file(path):
    """计算文件内容的 md5（十六进制小写）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_record_hash(file_hash, prev_hash, ts):
    """哈希链 v2 公式：record_hash = md5(file_hash + prev_hash + str(ts))"""
    return hashlib.md5((file_hash + prev_hash + str(ts)).encode()).hexdigest()


def main():
    # 1. 读取首条记录时间戳作为记忆起点
    first = load_first_chain_record(CHAIN_LOG)
    origin_ts = float(first["timestamp"])
    anomaly = None

    # 2. 若早于 2026-08-22，记录异常，仍以保守起点为准
    if origin_ts < CONSERVATIVE_LOWER_TS:
        anomaly = {
            "type": "early_origin",
            "first_ts": origin_ts,
            "first_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(origin_ts)),
            "note": "首条记录早于2026-08-22，采用2026-08-22作为保守起点，避免跨年错误匹配",
        }
        origin_ts = CONSERVATIVE_LOWER_TS
        origin_iso = CONSERVATIVE_ISO
    else:
        origin_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(origin_ts))

    # 3. 生成记忆起点记录
    record = {
        "schema_version": 2,
        "timestamp": time.time(),
        "memory_start": origin_ts,
        "memory_start_iso": origin_iso,
        "source": "luoshen_memory_origin",
    }
    if anomaly is not None:
        record["anomaly"] = anomaly

    with open(ORIGIN_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 4. 控制台打印记忆起点
    print("memory_start_ts =", origin_ts)
    print("memory_start_iso =", origin_iso)

    # 5. 哈希链追加：为 origin jsonl 计算 md5，读取当前链尾，按 v2 公式追加一条
    tail = read_chain_tail_record(CHAIN_LOG)
    prev_hash = tail["record_hash"]
    origin_file_hash = md5_of_file(ORIGIN_JSONL)
    append_ts = time.time()
    new_record = {
        "schema_version": 2,
        "timestamp": append_ts,
        "file": ORIGIN_JSONL,
        "file_hash": origin_file_hash,
        "prev_hash": prev_hash,
        "record_hash": compute_record_hash(origin_file_hash, prev_hash, append_ts),
    }
    with open(CHAIN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(new_record, ensure_ascii=False) + "\n")

    print("origin_file_md5 =", origin_file_hash)
    print("appended_record_hash =", new_record["record_hash"])
    print("prev_hash =", prev_hash)


if __name__ == "__main__":
    main()
