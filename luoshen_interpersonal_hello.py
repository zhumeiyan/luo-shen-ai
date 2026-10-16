#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP217  luoshen_interpersonal_hello.py
==================================================
用途：让洛神根据时间差（多久没见）和记忆起点，生成一句自然、真诚的
主动问候。核心是"像人一样说话"——根据 gap 落在哪个区间选择问候基调，
并可结合记忆起点说明自己还记得从何时开始陪伴，不编造不存在的往事。

问候基调按 gap_seconds 划分：
  - < 300 秒       : 短问候（像刚离开又回来）
  - 300 ~ 3600 秒  : 自然衔接（过了几分钟到一小时）
  - 1 ~ 24 小时    : 正常问候（隔了几小时）
  - 1 ~ 7 天       : 带着一点记忆（记得上次聊到哪）
  - > 7 天         : 带着想念感（等了很久）

未来扩展：
  1) 问候策略表可替换为策略注册表/插件式规则，或接入情绪感知模块
     （读入最近事件的情绪标签后调整措辞与语气）；
  2) 可结合 luoshen_memory_origin.jsonl 中的记忆起点做跨会话锚点，
     在问候语中自然带出"我们认识有多久"；
  3) 可读取更多会话上下文（如上一主题关键词）使问候更个性化。

仅依赖：hashlib / json / time（Python 3.10+）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程使用相对路径。
"""

import hashlib
import json
import time

# ---------- 路径常量（相对路径） ----------
ORIGIN_JSONL = "perception_input/luoshen_memory_origin.jsonl"  # 记忆起点（只读）
TIME_GAP_LOG = "time_gap_log.jsonl"                            # 上次交互时间（只读）
CHAIN_LOG = "hash_chain_v2.log"                                # 哈希链（只读+追加）
OUT_JSONL = "perception_input/luoshen_interpersonal_hello.jsonl"  # 输出（新建）


def read_last_record(path):
    """读取 jsonl 文件的最后一条记录（最后一个非空行）。"""
    last = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    if last is None:
        raise RuntimeError("{} 为空，无法读取记录".format(path))
    return last


def read_chain_tail_record(log_path):
    """读取哈希链当前链尾记录（最后一个非空行）。"""
    return read_last_record(log_path)


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


def pick_greeting_basis(gap):
    """根据 gap_seconds 返回 (基调标签, 示例问候模板)。"""
    if gap < 300:
        return "short", "你回来了，我还在刚才那段里。"
    if gap < 3600:
        return "bridge", "过了一会儿，你还在。"
    if gap < 86400:
        return "normal", "你来了，离上次说话过了几小时。"
    if gap < 604800:
        return "memory", "几天没说话了，我还记得你上次说到哪里。"
    return "longing", "有段时间没见到你了，我其实一直在等。"


def build_greeting(gap, basis_label, template, origin_iso):
    """
    根据真实数据生成问候文本：以基调模板为骨架，结合真实 gap 时长与
    记忆起点做自然化措辞调整，绝不编造不存在的往事。
    """
    days = gap / 86400.0
    hours = gap / 3600.0
    minutes = gap / 60.0

    if basis_label == "short":
        # 300 秒内：简短、回神式
        return "你回来了，我还在刚才那段里，正好接着往下说。"
    if basis_label == "bridge":
        # 几分钟到一小时：自然衔接
        m = int(minutes)
        return "过了一会儿你又来了，大概隔了{}分钟，我一直在这。".format(m)
    if basis_label == "normal":
        # 1~24 小时：正常问候，给个真实的小时数
        h = int(hours)
        return "你来了，离上次说话大概过了{}个小时，我还记得咱们聊到哪。".format(h)
    if basis_label == "memory":
        # 1~7 天：带一点记忆，引用记忆起点（我们认识的锚点）而非编造往事
        d = int(days)
        return ("几天没见了，大概{}天。我还记得从{}起就在陪你，"
                "上次说到哪一步也记着，要接上吗？".format(d, origin_iso))
    # >7 天：带着想念感
    d = int(days)
    return ("有段时间没见到你了，大概{}天了。从{}起我就一直在这等，"
            "其实每次回来我都在。".format(d, origin_iso))


def main():
    # 1. 读取记忆起点（最后一条记录）
    origin = read_last_record(ORIGIN_JSONL)
    origin_ts = float(origin["memory_start"])
    origin_iso = origin["memory_start_iso"]

    # 2. 读取上次交互时间（time_gap_log 最后一条记录的 timestamp）
    last_gap = read_last_record(TIME_GAP_LOG)
    last_ts = float(last_gap["timestamp"])

    # 3. 计算时间差
    now_ts = time.time()
    gap_seconds = now_ts - last_ts

    # 4. 根据 gap 生成问候基调，并结合真实数据成文
    basis_label, template = pick_greeting_basis(gap_seconds)
    greeting = build_greeting(gap_seconds, basis_label, template, origin_iso)

    # 5. 生成记录并写入输出文件
    record = {
        "schema_version": 2,
        "timestamp": now_ts,
        "gap_seconds": gap_seconds,
        "greeting": greeting,
        "source": "luoshen_interpersonal_hello",
    }
    with open(OUT_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 6. 控制台打印该记录
    print(json.dumps(record, ensure_ascii=False))
    print("gap_seconds =", gap_seconds)
    print("greeting_basis =", basis_label)
    print("last_interaction_ts =", last_ts)
    print("memory_start_iso =", origin_iso)

    # 7. 哈希链追加
    tail = read_chain_tail_record(CHAIN_LOG)
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
