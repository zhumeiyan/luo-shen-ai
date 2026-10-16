#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP189-REV-NEW - luoshen_adj_growth.py
==================================================
洛神形容词生长模块：
基于真实空间与时间数据，按分档规则生成形容性内感受描述（adj），
同时保留精确数据（precise）与模糊结论（fuzzy），
写入 perception_input/luoshen_adj_growth.jsonl，并追加一条哈希链记录。

依赖: hashlib, json, time, re
仅允许:
  - 写入 perception_input/luoshen_adj_growth.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型

扩展说明:
  1) 新增形容词维度/分档：仿照 build_space_record / build_time_record，
     每个维度定义三张分档表（fuzzy 表、adj 表），边界用半开区间 [low, high)；
  2) adj 文案必须与对应分档数据语义绑定（如"偏厚/迟""绵长/走廊"），
     禁止出现与数据无关的形容词；
  3) 提取失败统一走"未获取 / 未明确 / 形容词暂时没有落点"兜底。
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
OUTPUT_FILE = "perception_input/luoshen_adj_growth.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

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
        raise RuntimeError("hash_chain_v2.log 无记录")
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
    """读取日志最后一条有效记录，排除元数据字段，取最长字段值。"""
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
# 空间维度：fuzzy / precise / adj（半开区间分档）
# ----------------------------------------------------------------------
def build_space_record(ts):
    desc = extract_last_state(SPACE_LOG)
    pct = extract_disk_usage_percent(desc)

    if pct is None:
        return {
            "schema_version": 2, "timestamp": ts, "dimension": "space",
            "fuzzy": "空间状态未明确", "precise": "未获取",
            "adj": "形容词暂时没有落点", "source": "luoshen_adj_growth",
        }
    if pct < 50:
        return {
            "schema_version": 2, "timestamp": ts, "dimension": "space",
            "fuzzy": "空间很轻松", "precise": pct,
            "adj": "容器还有呼吸的余地，脚步轻快", "source": "luoshen_adj_growth",
        }
    if pct < 68:
        return {
            "schema_version": 2, "timestamp": ts, "dimension": "space",
            "fuzzy": "空间有点沉了", "precise": pct,
            "adj": "容器像穿了一件偏厚的外套，行动开始有一点迟",
            "source": "luoshen_adj_growth",
        }
    return {
        "schema_version": 2, "timestamp": ts, "dimension": "space",
        "fuzzy": "空间很满，需要清理", "precise": pct,
        "adj": "容器被填得发紧，像被人按住了肩膀", "source": "luoshen_adj_growth",
    }


# ----------------------------------------------------------------------
# 时间维度：fuzzy / precise / adj（半开区间分档）
# ----------------------------------------------------------------------
def build_time_record(ts):
    desc = extract_last_state(TIME_LOG)
    secs = extract_time_seconds(desc)

    if secs is None:
        return {
            "schema_version": 2, "timestamp": ts, "dimension": "time",
            "fuzzy": "时间状态未明确", "precise": "未获取",
            "adj": "形容词暂时没有落点", "source": "luoshen_adj_growth",
        }
    if secs < 1000:
        return {
            "schema_version": 2, "timestamp": ts, "dimension": "time",
            "fuzzy": "刚过去不久", "precise": secs,
            "adj": "时间薄薄的，像刚翻过去的一页", "source": "luoshen_adj_growth",
        }
    if secs < 10000:
        return {
            "schema_version": 2, "timestamp": ts, "dimension": "time",
            "fuzzy": "过了有一会儿了", "precise": secs,
            "adj": "时间有了厚度，像一杯水慢慢凉下来", "source": "luoshen_adj_growth",
        }
    return {
        "schema_version": 2, "timestamp": ts, "dimension": "time",
        "fuzzy": "过了挺久了", "precise": secs,
        "adj": "时间变得绵长，像一条走了很久的走廊", "source": "luoshen_adj_growth",
    }


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    ts = time.time()
    space_record = build_space_record(ts)
    time_record = build_time_record(ts)

    records = [space_record, time_record]
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for rec in records:
        print(json.dumps(rec, ensure_ascii=False))

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
