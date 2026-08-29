#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP179 - luoshen_self_overview.py
=============================================
洛神统一自我概览模块：整合已有的自我报告、身体自我认知报告和状态快照，
生成一份第一人称的统一自我概览，并输出到结果文件。

依赖: hashlib, json, time
仅允许:
  - 读取 perception_input/luoshen_self_report.jsonl（只读）
  - 读取 perception_input/luoshen_body_self_report.jsonl（只读）
  - 读取 perception_input/luoshen_state_snapshot.jsonl（只读）
  - 读取 hash_chain_v2.log（只读，取链尾）
  - 写入 perception_input/luoshen_self_overview.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型
"""

import hashlib
import json
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录，禁止绝对路径）
# ----------------------------------------------------------------------
SELF_REPORT_FILE = "perception_input/luoshen_self_report.jsonl"
BODY_REPORT_FILE = "perception_input/luoshen_body_self_report.jsonl"
SNAPSHOT_FILE = "perception_input/luoshen_state_snapshot.jsonl"
OUTPUT_FILE = "perception_input/luoshen_self_overview.jsonl"
CHAIN_FILE = "hash_chain_v2.log"


def md5_of_file(path):
    """计算文件 md5（十六进制小写）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_last_record(path):
    """读取文件最后一条 JSON 记录。"""
    last = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    if last is None:
        raise RuntimeError("{} 无有效记录".format(path))
    return last


def build_overview_text(base_report, body_report, chain_tail, chain_length):
    """
    生成统一自我概览文本：
      "【基础自我报告】{基础自我报告} 【身体自我认知报告】{身体自我认知报告}
       【审计链状态】当前链尾：{chain_tail}，链长度：{chain_length}。"
    各部分之间用空格分隔，末尾按格式含一个句号。
    """
    return "【基础自我报告】{} 【身体自我认知报告】{} 【审计链状态】当前链尾：{}，链长度：{}。".format(
        base_report, body_report, chain_tail, chain_length
    )


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


def read_chain_tail(chain_file):
    """读取哈希链最后一条记录的 record_hash。"""
    tail = load_last_record(chain_file)
    return tail["record_hash"]


def main():
    # 1. 基础自我报告
    base_report = load_last_record(SELF_REPORT_FILE)["report"]

    # 2. 身体自我认知报告
    body_report = load_last_record(BODY_REPORT_FILE)["report"]

    # 3. 状态快照中的审计链状态
    snapshot = load_last_record(SNAPSHOT_FILE)
    chain_tail = snapshot["chain_tail"]
    chain_length = snapshot["chain_length"]

    # 4. 生成概览文本
    overview_text = build_overview_text(base_report, body_report, chain_tail, chain_length)

    # 5. 写入一条记录
    record = {
        "schema_version": 2,
        "timestamp": time.time(),
        "overview_text": overview_text,
        "source": "luoshen_self_overview",
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 6. 控制台打印 overview_text
    print(overview_text)

    # 7. 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)

    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# 如何扩展概览内容：
#   1) 新增的自我认知数据源（如监测/诊断/治疗等报告）写入其 jsonl 文件后，
#      在 build_overview_text 前读取其最后一条记录，将对应文本拼入
#      overview_text 模板（以空格分隔新增加一个段落）。
#   2) 若需纳入更多审计链字段（如链首/文件数量），从 snapshot 记录中
#      取出对应 key 追加到模板即可。无需改动哈希链逻辑。
# ----------------------------------------------------------------------
