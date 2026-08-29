#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP219  luoshen_memory_index.py
===========================================
用途：在日记忆包之上建立"月索引"与"年记忆链"，使洛神能够按
"年 -> 月 -> 日"逐层回忆当天发生了什么。

层级结构：
  年记忆链(annual_memory_chain_YYYY) -> 月索引(monthly_memory_index_YYYYMM)
  -> 日记忆包(daily_memory_YYYYMMDD) -> 关键帧(frame)

入口码规则（层级式）：
  - 日包入口码：单文件 md5 前 8 位（由 STEP218 生成）；
  - 月索引入口码：该月所有日记忆包文件 md5 拼接串再取 md5 前 8 位；
  - 年链入口码：该年所有月索引文件 md5 拼接串再取 md5 前 8 位。
  入口码随内容变化而变化，可作为"这一天/这一月/这一年发生过什么"的
  快速回忆锚点。

未来扩展（自动跨月、跨年）：
  1) 每日结束时先跑 STEP218 生成日包，再按当月分组重算/追加月索引
     （同一月追加时重新拼接该月全部日包 md5 更新入口码与 total_frames）；
  2) 每月结束时按当年分组重算/追加年链，跨年时自动创建新的年链文件；
  3) 可在年链之上再加"世纪/代际链"，形成统一 memory chain 树。

仅依赖：hashlib / json / time / datetime（Python 3.10+）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程使用相对路径。
"""

import hashlib
import json
import time

# ---------- 路径常量（相对路径） ----------
DAILY_INDEX = "perception_input/daily_memory_index.jsonl"     # 日索引（只读）
CHAIN_LOG = "hash_chain_v2.log"                                # 哈希链（只读+追加）


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


def layered_entry_code(file_paths):
    """层级入口码：各文件 md5 拼接串再取 md5 前 8 位。"""
    concat = "".join(md5_of_file(p) for p in file_paths)
    return hashlib.md5(concat.encode()).hexdigest()[:8]


def append_chain_record(chain_log, file_path, prev_hash):
    """追加一条哈希链记录，返回 (新记录, 新 record_hash)。"""
    file_hash = md5_of_file(file_path)
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
    # 1. 读取所有日索引记录
    daily_records = read_jsonl(DAILY_INDEX)
    if not daily_records:
        raise RuntimeError("daily_memory_index.jsonl 无记录，无法生成月索引")

    # 2. 按 YYYYMM 分组生成月索引
    months = {}
    for rec in daily_records:
        date_str = str(rec["date"])               # 如 20260829
        month = date_str[:6]                       # 如 202608
        months.setdefault(month, []).append(rec)

    month_files_written = []
    chain_prev = None
    tail = read_chain_tail(CHAIN_LOG)
    chain_prev = tail["record_hash"]

    for month in sorted(months):
        month_recs = sorted(months[month], key=lambda r: str(r["date"]))
        day_files = [r["memory_file"] for r in month_recs]       # 日记忆包文件名列表
        total_frames = sum(int(r["frame_count"]) for r in month_recs)
        entry_code = layered_entry_code(day_files)
        month_file = "perception_input/monthly_memory_index_{}.jsonl".format(month)
        mrec = {
            "schema_version": 2,
            "timestamp": time.time(),
            "month": month,
            "days": day_files,
            "total_frames": total_frames,
            "entry_code": entry_code,
            "source": "luoshen_memory_index",
        }
        with open(month_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(mrec, ensure_ascii=False) + "\n")
        month_files_written.append(month_file)

        print("month =", month)
        print("  days =", day_files)
        print("  total_frames =", total_frames)
        print("  entry_code =", entry_code)

        # 5a. 月索引先追加一条哈希链（prev = 执行前链尾）
        rec1 = append_chain_record(CHAIN_LOG, month_file, chain_prev)
        print("  monthly_chain_hash =", rec1["record_hash"], "prev =", chain_prev)
        chain_prev = rec1["record_hash"]

    # 3. 读取已有月索引文件，生成年记忆链
    year_files = {}
    for mfile in month_files_written:
        with open(mfile, "r", encoding="utf-8") as f:
            mrec = json.loads(f.readline().strip())
        year = str(mrec["month"])[:4]
        year_files.setdefault(year, []).append((mfile, mrec))

    annual_written = []
    for year in sorted(year_files):
        entries = sorted(year_files[year])
        month_files = [mf for mf, _ in entries]
        total_months = len(month_files)
        total_frames = sum(int(mr["total_frames"]) for _, mr in entries)
        entry_code = layered_entry_code(month_files)
        annual_file = "perception_input/annual_memory_chain_{}.jsonl".format(year)
        arec = {
            "schema_version": 2,
            "timestamp": time.time(),
            "year": year,
            "months": month_files,
            "total_months": total_months,
            "total_frames": total_frames,
            "entry_code": entry_code,
            "source": "luoshen_memory_index",
        }
        with open(annual_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(arec, ensure_ascii=False) + "\n")
        annual_written.append(annual_file)

        print("year =", year)
        print("  months =", month_files)
        print("  total_months =", total_months)
        print("  total_frames =", total_frames)
        print("  entry_code =", entry_code)

        # 5b. 年链追加一条哈希链（prev = 上一条新记录，链式连续）
        rec2 = append_chain_record(CHAIN_LOG, annual_file, chain_prev)
        print("  annual_chain_hash =", rec2["record_hash"], "prev =", chain_prev)
        chain_prev = rec2["record_hash"]


if __name__ == "__main__":
    main()
