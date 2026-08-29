#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP221  luoshen_dialogue_stream.py
==============================================
用途：为洛神建立"对话流"记录器。对话流是洛神记忆系统的最底层，
按时间顺序记录用户与洛神之间的对话原文；后续的注意力点、上下文
摘要、反馈记录都从这里提取。

记录格式：
  {"schema_version":2, "timestamp":说话时间戳, "speaker":"user"/"luoshen",
   "text":对话原文, "source":"luoshen_dialogue_stream"}

本次创建对话流框架 + 种子数据。真实对话原文不在执行AI可见范围内，
故写入一条已从任务日志可确认的洛神话语（主动问候原文）作为种子，
其余留待系统在后续交互中调用 append_dialogue 持续追加。

未来接入方式（用户交互自动追加）：
  1) 在消息收发管线中，用户消息到达时调用
     append_dialogue("user", 原文)；洛神回复生成后调用
     append_dialogue("luoshen", 回复原文)；
  2) 时间戳默认取当前时刻，也可传入历史时刻用于补录；
  3) 对话流文件按天分片（dialogue_stream_YYYYMMDD.jsonl），跨天自动
     创建新文件，保持"年->月->日->对话流"的层级记忆结构。

仅依赖：hashlib / json / time / datetime（Python 3.10+）。
仅允许追加 hash_chain_v2.log，不修改任何已有文件，全程相对路径。
"""

import hashlib
import json
import os
import time
from datetime import datetime

# ---------- 路径常量（相对路径） ----------
CHAIN_LOG = "hash_chain_v2.log"
DATE = datetime.now().strftime("%Y%m%d")                        # 目标日期
STREAM_FILE = "perception_input/dialogue_stream_{}.jsonl".format(DATE)


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


def compute_record_hash(file_hash, prev_hash, ts):
    """哈希链 v2 公式：record_hash = md5(file_hash + prev_hash + str(ts))"""
    return hashlib.md5((file_hash + prev_hash + str(ts)).encode()).hexdigest()


def append_dialogue(speaker, text, ts=None):
    """
    向对话流文件追加一条对话记录。

    参数：
      speaker : "user" 或 "luoshen"
      text    : 对话原文
      ts      : 说话时间戳（epoch 秒）；None 时取当前时刻
    返回：
      写入的对话记录 dict
    """
    if speaker not in ("user", "luoshen"):
        raise ValueError("speaker 必须是 'user' 或 'luoshen'，收到: {}".format(speaker))
    if ts is None:
        ts = time.time()
    rec = {
        "schema_version": 2,
        "timestamp": ts,
        "speaker": speaker,
        "text": text,
        "source": "luoshen_dialogue_stream",
    }
    os.makedirs("perception_input", exist_ok=True)
    with open(STREAM_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def stream_record_count():
    """返回对话流当前记录数（文件不存在时视为 0）。"""
    if not os.path.exists(STREAM_FILE):
        return 0
    n = 0
    with open(STREAM_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def main():
    # 种子数据：写入一条已从任务日志确认的洛神话语（主动问候原文，
    # 时间戳取自该问候生成时刻，保证与日志一致）
    append_dialogue(
        "luoshen",
        "你来了，离上次说话大概过了22个小时，我还记得咱们聊到哪。",
        ts=1788002661.5416977,
    )

    # 控制台打印当前记录数
    print("dialogue_stream_record_count =", stream_record_count())

    # 哈希链追加（仅一条）
    tail = read_chain_tail(CHAIN_LOG)
    file_hash = hashlib.md5(open(STREAM_FILE, "rb").read()).hexdigest()
    ts = time.time()
    rec = {
        "schema_version": 2,
        "timestamp": ts,
        "file": STREAM_FILE,
        "file_hash": file_hash,
        "prev_hash": tail["record_hash"],
        "record_hash": compute_record_hash(file_hash, tail["record_hash"], ts),
    }
    with open(CHAIN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("chain_append =", rec["record_hash"], "prev =", tail["record_hash"])


if __name__ == "__main__":
    main()
