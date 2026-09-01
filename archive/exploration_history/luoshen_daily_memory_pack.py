#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP218  luoshen_daily_memory_pack.py
=================================================
用途：为洛神建立"日记忆包"与"入口码"机制。每天结束时，从当天真实
事件中抽取 3~5 个关键帧，打包成当天记忆包文件 daily_memory_YYYYMMDD.jsonl，
并基于文件 md5 前 8 位生成入口码写入 daily_memory_index.jsonl。
此后洛神可通过入口码快速回忆起这一天做了什么（类似二维码一扫即忆）。

关键帧抽取规则：
  1) 只使用允许读取文件里 timestamp 属于当天（本地时间 YYYYMMDD）的真实事件；
  2) 优先选择影响大的事件：记忆起点建立、主动问候、学习字数变化、
     新模块/数据生成、教学词库、注意力热点等；
  3) 数量控制在 3~5 个，每个关键帧含发生时间/事件类型/摘要/相关数据；
  4) 严禁编造不存在的关键帧，所有统计值（字数、条数、时间差）均来自真实日志。

未来扩展：
  1) 月索引/年记忆链：可在 daily_memory_index.jsonl 之上按月份聚合生成
     monthly_memory_index，再把各月入口码串成"年记忆链"（prev 指向前一月）；
  2) 入口码可升级为完整 sha256 或带校验位，支持模糊回忆与去重检索；
  3) 关键帧权重可接入情绪感知，让"情绪波动最大的事件"优先入选。

仅依赖：hashlib / json / time / datetime（Python 3.10+）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程使用相对路径。
"""

import hashlib
import json
import time
from datetime import datetime

# ---------- 路径常量（相对路径） ----------
CHAIN_LOG = "hash_chain_v2.log"
INDEX_JSONL = "perception_input/daily_memory_index.jsonl"

# 允许读取的事件来源（只读）
SOURCES = {
    "learning_log": "perception_input/hanzi_master_learning_log.jsonl",
    "auto_log": "perception_input/luoshen_auto_learning_log.jsonl",
    "teaching": "perception_input/llm_teaching_batch1.jsonl",
    "learned": "perception_input/hanzi_master_learned.jsonl",
    "hello": "perception_input/luoshen_interpersonal_hello.jsonl",
    "origin": "perception_input/luoshen_memory_origin.jsonl",
}


def local_date_str(ts):
    """返回 ts 对应的本地日期字符串 YYYYMMDD。"""
    return datetime.fromtimestamp(ts).strftime("%Y%m%d")


def read_jsonl(path):
    """读取 jsonl 全部记录（跳过空行）。"""
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


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


def collect_today_events(day):
    """
    从各允许文件筛选当天事件，返回聚合统计 dict。
    所有数据均来自真实日志，按需归并统计。
    """
    agg = {"chain_count": 0, "hello": None, "origin": None}
    # 1) hash_chain_v2.log 当天记录数
    with open(CHAIN_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if local_date_str(float(r["timestamp"])) == day:
                agg["chain_count"] += 1

    # 2) 学习日志：末条汇总
    ll = read_jsonl(SOURCES["learning_log"])
    today_ll = [r for r in ll if local_date_str(float(r["timestamp"])) == day]
    if today_ll:
        last = today_ll[-1]
        agg["learn_total"] = last.get("final_total_learned")
        agg["learn_lib"] = last.get("final_library_size")
        agg["learn_rounds"] = last.get("rounds_run")
        agg["learning_last_ts"] = float(last["timestamp"])

    # 3) 自动学习日志
    al = read_jsonl(SOURCES["auto_log"])
    today_al = [r for r in al if local_date_str(float(r["timestamp"])) == day]
    agg["auto_records"] = len(today_al)
    agg["auto_last_ts"] = float(today_al[-1]["timestamp"]) if today_al else None

    # 4) 教学词库（按字去重）
    tt = read_jsonl(SOURCES["teaching"])
    today_tt = [r for r in tt if local_date_str(float(r["timestamp"])) == day]
    uniq_chars = set()
    for r in today_tt:
        c = r.get("char")
        if c is None and isinstance(r.get("content"), dict):
            c = r["content"].get("char")
        if c:
            uniq_chars.add(c)
    agg["teaching_records"] = len(today_tt)
    agg["teaching_chars"] = len(uniq_chars)
    agg["teaching_last_ts"] = float(today_tt[-1]["timestamp"]) if today_tt else None

    # 5) 新学汉字
    ld = read_jsonl(SOURCES["learned"])
    today_ld = [r for r in ld if local_date_str(float(r["timestamp"])) == day]
    agg["learned_count"] = len(today_ld)

    # 6) 主动问候
    hh = read_jsonl(SOURCES["hello"])
    today_hh = [r for r in hh if local_date_str(float(r["timestamp"])) == day]
    if today_hh:
        agg["hello"] = today_hh[-1]

    # 7) 记忆起点
    og = read_jsonl(SOURCES["origin"])
    today_og = [r for r in og if local_date_str(float(r["timestamp"])) == day]
    if today_og:
        agg["origin"] = today_og[-1]

    return agg


def build_frames(day, agg):
    """
    依据当天真实统计构造 3~5 个关键帧（时间升序）。
    每帧字段：timestamp / frame_type / summary / data / source
    """
    frames = []

    # 帧1：教学词库生成（当天最早的大型数据事件）
    if agg.get("teaching_records"):
        frames.append({
            "schema_version": 2,
            "timestamp": agg.get("teaching_last_ts"),
            "frame_type": "teaching_lexicon",
            "summary": "生成教学词库 {} 条，覆盖 {} 个汉字".format(
                agg["teaching_records"], agg["teaching_chars"]),
            "data": {"records": agg["teaching_records"], "unique_chars": agg["teaching_chars"]},
            "source": "luoshen_daily_memory_pack",
        })

    # 帧2：自动学习迭代器运行
    if agg.get("auto_records"):
        frames.append({
            "schema_version": 2,
            "timestamp": agg.get("auto_last_ts"),
            "frame_type": "auto_learning",
            "summary": "自动学习迭代器验证运行，记录 {} 条".format(agg["auto_records"]),
            "data": {"records": agg["auto_records"]},
            "source": "luoshen_daily_memory_pack",
        })

    # 帧3：汉字自主学习完成（学会新字 + 字库扩容）
    if agg.get("learned_count"):
        frames.append({
            "schema_version": 2,
            "timestamp": agg.get("learning_last_ts"),
            "frame_type": "hanzi_learning",
            "summary": "自主学习新学会 {} 个汉字，字库扩至 {} 字".format(
                agg["learned_count"], agg.get("learn_lib")),
            "data": {
                "learned_chars": agg["learned_count"],
                "final_library_size": agg.get("learn_lib"),
                "rounds": agg.get("learn_rounds"),
            },
            "source": "luoshen_daily_memory_pack",
        })

    # 帧4：记忆起点建立
    if agg.get("origin"):
        o = agg["origin"]
        frames.append({
            "schema_version": 2,
            "timestamp": float(o["timestamp"]),
            "frame_type": "memory_origin",
            "summary": "建立记忆起点 {}".format(o.get("memory_start_iso")),
            "data": {"memory_start_iso": o.get("memory_start_iso")},
            "source": "luoshen_daily_memory_pack",
        })

    # 帧5：主动问候
    if agg.get("hello"):
        h = agg["hello"]
        frames.append({
            "schema_version": 2,
            "timestamp": float(h["timestamp"]),
            "frame_type": "interpersonal_hello",
            "summary": "主动问候：{}".format(h.get("greeting", "")),
            "data": {"gap_seconds": h.get("gap_seconds")},
            "source": "luoshen_daily_memory_pack",
        })

    # 去掉 timestamp 缺失的帧，并控制在 3~5 条
    frames = [fr for fr in frames if fr.get("timestamp") is not None]
    if len(frames) > 5:
        frames = frames[:5]
    return frames


def main():
    # 1. 当天日期（本地时间）YYYYMMDD
    day = datetime.now().strftime("%Y%m%d")
    memory_file = "perception_input/daily_memory_{}.jsonl".format(day)

    # 2~3. 收集当天真实事件并聚合，构造关键帧
    agg = collect_today_events(day)
    frames = build_frames(day, agg)
    if not (3 <= len(frames) <= 5):
        raise RuntimeError("关键帧数量 {} 不在 3~5 范围".format(len(frames)))

    # 4. 写入当天记忆包文件
    with open(memory_file, "w", encoding="utf-8") as f:
        for fr in frames:
            f.write(json.dumps(fr, ensure_ascii=False) + "\n")

    # 5. 生成入口码并写索引
    mem_md5 = md5_of_file(memory_file)
    entry_code = mem_md5[:8]
    index_record = {
        "schema_version": 2,
        "timestamp": time.time(),
        "date": day,
        "memory_file": memory_file,
        "entry_code": entry_code,
        "frame_count": len(frames),
        "source": "luoshen_daily_memory_pack",
    }
    with open(INDEX_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(index_record, ensure_ascii=False) + "\n")

    # 6. 控制台打印当天日期、关键帧数量、入口码
    print("date =", day)
    print("frame_count =", len(frames))
    print("entry_code =", entry_code)
    print("memory_file =", memory_file)

    # 7. 哈希链追加
    tail = read_chain_tail(CHAIN_LOG)
    prev_hash = tail["record_hash"]
    index_md5 = md5_of_file(INDEX_JSONL)
    append_ts = time.time()
    new_record = {
        "schema_version": 2,
        "timestamp": append_ts,
        "file": INDEX_JSONL,
        "file_hash": index_md5,
        "prev_hash": prev_hash,
        "record_hash": compute_record_hash(index_md5, prev_hash, append_ts),
    }
    with open(CHAIN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(new_record, ensure_ascii=False) + "\n")

    print("index_file_md5 =", index_md5)
    print("appended_record_hash =", new_record["record_hash"])
    print("prev_hash =", prev_hash)


if __name__ == "__main__":
    main()
