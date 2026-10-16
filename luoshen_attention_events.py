#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP220  luoshen_attention_events.py
===============================================
用途：为洛神建立"注意力点"提取与事件级时间线，解决"只记得几帧、
忘了具体哪个点"的问题——不仅能记住一天的整体摘要，还能定位到
每个重要瞬间的具体时间、原话或关键数据。

注意力点定义：当天对话或任务中出现的关键灵感、转折、重要判断、
异常事件、任务完成时刻。本实现从当天各日志中提取：
  - 重要任务完成（词库生成 / 自动学习 / 字库扩容 / 记忆起点 /
    日记忆包 / 月索引 / 年链 等）
  - 情绪性 / 人际性表达（主动问候原文）
  - 重要判断（时间感知结果）

未来扩展（更多日期 / 实时提取）：
  1) 把目标日期改为参数（如 --date=YYYYMMDD），按日期扫描对应
     日志文件即可复用同一套提取逻辑；
  2) 实时提取可常驻监听日志尾部（tail -f 模式），新记录到达即
     触发注意力点判定并追加写入当天文件；
  3) 可增加"用户新概念 / 异常返工"等关键词规则（如包含
     "新概念""返工""重跑"），把判定函数 attention_score() 做成
     可插拔规则表。

仅依赖：hashlib / json / time / datetime（Python 3.10+）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程相对路径。
"""

import hashlib
import json
import time
from datetime import datetime, timezone

# ---------- 路径常量（相对路径） ----------
TARGET_DATE = "20260829"                                        # 目标日期
CHAIN_LOG = "hash_chain_v2.log"
OUT_FILE = "perception_input/attention_events_{}.jsonl".format(TARGET_DATE)

EVENT_FILES = [
    "perception_input/llm_teaching_batch1.jsonl",               # 教学词库
    "perception_input/hanzi_master_learning_log.jsonl",         # 自主学习
    "perception_input/luoshen_memory_origin.jsonl",             # 记忆起点
    "perception_input/luoshen_interpersonal_hello.jsonl",       # 主动问候
    "perception_input/luoshen_time_sense.jsonl",                # 时间感知
    "perception_input/daily_memory_20260829.jsonl",             # 日记忆包帧
]


def read_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def utc_date(ts):
    """epoch 秒 -> UTC 日期字符串 YYYYMMDD。"""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")


def read_chain_tail(log_path):
    tail = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("{} 为空，无法读取链尾".format(log_path))
    return tail


def compute_record_hash(file_hash, prev_hash, ts):
    return hashlib.md5((file_hash + prev_hash + str(ts)).encode()).hexdigest()


def append_chain_record(chain_log, file_path, prev_hash):
    file_hash = hashlib.md5(open(file_path, "rb").read()).hexdigest()
    ts = time.time()
    rec = {
        "schema_version": 2,
        "timestamp": ts,
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": compute_record_hash(file_hash, prev_hash, ts),
    }
    with open(chain_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main():
    # 候选注意力点池：(timestamp, attention_point, source_file)
    candidates = []

    # 1) 教学词库批量生成（380 条同 ts，聚合为一条）
    teaching = read_jsonl(EVENT_FILES[0])
    teaching_ts = teaching[0]["timestamp"] if teaching else None
    unique_chars = None
    for rec in read_jsonl(EVENT_FILES[5]):
        if rec.get("frame_type") == "teaching_lexicon":
            unique_chars = rec.get("data", {}).get("unique_chars")
            break
    if teaching_ts is not None and utc_date(teaching_ts) == TARGET_DATE:
        if unique_chars is not None:
            point = "教学词库批量生成 {} 条，覆盖 {} 个汉字".format(len(teaching), unique_chars)
        else:
            point = "教学词库批量生成 {} 条".format(len(teaching))
        candidates.append((teaching_ts, point, EVENT_FILES[0]))

    # 2) 自主学习：取末条 final 汇总记录
    learn = read_jsonl(EVENT_FILES[1])
    final_rec = None
    for rec in learn:
        if "final_total_learned" in rec:
            final_rec = rec
    if final_rec is not None and utc_date(final_rec["timestamp"]) == TARGET_DATE:
        candidates.append((final_rec["timestamp"],
                           "自主学习完成：{} 轮共新学会 {} 个汉字，字库扩至 {} 字".format(
                               final_rec["rounds_run"],
                               final_rec["final_total_learned"],
                               final_rec["final_library_size"]),
                           EVENT_FILES[1]))

    # 3) 记忆起点
    origin = read_jsonl(EVENT_FILES[2])
    if origin and utc_date(origin[0]["timestamp"]) == TARGET_DATE:
        candidates.append((origin[0]["timestamp"],
                           "建立记忆起点 {}".format(origin[0]["memory_start_iso"]),
                           EVENT_FILES[2]))

    # 4) 人际主动问候（保留原文）
    hello = read_jsonl(EVENT_FILES[3])
    if hello and utc_date(hello[0]["timestamp"]) == TARGET_DATE:
        candidates.append((hello[0]["timestamp"],
                           "主动问候：{}".format(hello[0]["greeting"]),
                           EVENT_FILES[3]))

    # 5) 时间感知（保留关键判断结果）
    tsense = read_jsonl(EVENT_FILES[4])
    if tsense and utc_date(tsense[0]["timestamp"]) == TARGET_DATE:
        candidates.append((tsense[0]["timestamp"],
                           "时间感知：当前 {}，距上次交互 {}".format(
                               tsense[0]["current_time"], tsense[0]["gap_human"]),
                           EVENT_FILES[4]))

    # 6) 日记忆包帧：补上独立文件未覆盖的 auto_learning 帧
    daily = read_jsonl(EVENT_FILES[5])
    covered_ts = {round(ts, 0) for ts, _, _ in candidates}
    for rec in daily:
        if utc_date(rec["timestamp"]) != TARGET_DATE:
            continue
        if round(rec["timestamp"], 0) in covered_ts:
            continue
        candidates.append((rec["timestamp"], rec["summary"], EVENT_FILES[5]))

    # 7) 哈希链当天节点：提取"索引/链构建"等任务完成事件
    chain = read_jsonl(CHAIN_LOG)
    for rec in chain:
        if utc_date(rec["timestamp"]) != TARGET_DATE:
            continue
        fname = rec["file"]
        if fname in ("perception_input/daily_memory_index.jsonl",
                     "perception_input/monthly_memory_index_202608.jsonl",
                     "perception_input/annual_memory_chain_2026.jsonl"):
            # 从对应文件读取关键内容
            with open(fname, "r", encoding="utf-8") as f:
                data = json.loads(f.readline().strip())
            if "entry_code" in data:
                detail = "入口码 {}".format(data["entry_code"])
                kind = "日记忆包" if fname.endswith("daily_memory_index.jsonl") else \
                       "月索引" if fname.endswith("monthly_memory_index_202608.jsonl") else "年记忆链"
                point = "生成{}，{}".format(kind, detail)
                candidates.append((rec["timestamp"], point, fname))

    # 去重（同秒视为同一事件，保留首个）并按时间排序
    dedup = {}
    for ts, point, src in candidates:
        key = round(ts, 0)
        if key not in dedup:
            dedup[key] = (ts, point, src)
    ordered = [dedup[k] for k in sorted(dedup)]

    # 写入注意力点文件
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for ts, point, src in ordered:
            rec = {
                "schema_version": 2,
                "timestamp": ts,
                "attention_point": point,
                "source_file": src,
                "source": "luoshen_attention_events",
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 控制台打印
    print("attention_point_count =", len(ordered))
    for i, (ts, point, src) in enumerate(ordered, 1):
        print("  [{}] ts={} | {} | src={}".format(i, ts, point, src))

    # 哈希链追加（仅一条）
    tail = read_chain_tail(CHAIN_LOG)
    rec = append_chain_record(CHAIN_LOG, OUT_FILE, tail["record_hash"])
    print("chain_append =", rec["record_hash"], "prev =", tail["record_hash"])


if __name__ == "__main__":
    main()
