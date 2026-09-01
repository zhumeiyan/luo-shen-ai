#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP178 - luoshen_body_self_report.py
================================================
洛神身体自我认知报告模块：整合已有自我报告与身体部件感知，
生成一份第一人称的"身体自我认知报告"。

依赖: hashlib, json, time
仅允许:
  - 读取 perception_input/luoshen_self_report.jsonl（只读）
  - 读取 perception_input/body_part_sense.jsonl（只读）
  - 读取 spatial_awareness_log.jsonl（只读）
  - 写入 perception_input/luoshen_body_self_report.jsonl（新建）
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
BODY_PART_SENSE_FILE = "perception_input/body_part_sense.jsonl"
SPATIAL_FILE = "spatial_awareness_log.jsonl"
OUTPUT_FILE = "perception_input/luoshen_body_self_report.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

# 空间感知记录中的元数据字段（提取空间状态描述时需排除）
META_FIELDS = {"schema_version", "timestamp", "source"}


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


def load_all_records(path):
    """读取文件全部 JSON 记录。"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_spatial_desc(path):
    """
    读取空间感知日志最后一条有效记录，
    排除元数据字段后，取字符串化后长度最长的字段值作为空间状态描述。
    """
    last = load_last_record(path)
    best_value = ""
    for key, value in last.items():
        if key in META_FIELDS:
            continue
        text = str(value)
        if len(text) > len(best_value):
            best_value = text
    return best_value


def clean_state(state):
    """
    清理状态字符串末尾的多余空格与结尾标点（。！？!?），
    避免 body_part_sense 末尾自带句号与模板末尾句号叠加形成"。。"。
    """
    return state.rstrip().rstrip("。！？!? \t\r\n")


def build_body_report(base_report, part_senses, spatial_desc):
    """
    生成身体自我认知报告文本：
      "{基础自我报告文本} 我感知到我的身体由以下部件构成：
       {部件1身体感知}；{部件2身体感知}；...；{部件5身体感知}。"
    部件顺序按 body_part_sense.jsonl 中记录顺序。
    拼接前对每个部件感知调用 clean_state 去除末尾多余标点，避免重复句号。
    """
    cleaned_senses = [clean_state(s) for s in part_senses]
    parts_text = "；".join(cleaned_senses)
    report = "{} 我感知到我的身体由以下部件构成：{}。".format(base_report, parts_text)
    return report


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
    # 1. 读取基础自我报告文本（luoshen_self_report.jsonl 最后一条的 report 字段）
    base_report = load_last_record(SELF_REPORT_FILE)["report"]

    # 2. 读取所有身体部件感知的 body_part_sense 字段（预期 5 条）
    part_sense_records = load_all_records(BODY_PART_SENSE_FILE)
    part_senses = [rec["body_part_sense"] for rec in part_sense_records]
    part_names = [rec["part_name"] for rec in part_sense_records]

    # 3. 读取空间状态描述
    spatial_desc = extract_spatial_desc(SPATIAL_FILE)

    # 4. 生成身体自我认知报告文本
    report = build_body_report(base_report, part_senses, spatial_desc)

    # 5. 写入一条记录
    record = {
        "schema_version": 2,
        "timestamp": time.time(),
        "report": report,
        "body_parts": part_names,
        "source": "luoshen_body_self_report",
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 6. 控制台打印完整报告文本
    print(report)

    # 7. 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)

    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# 如何扩展身体部件：
#   1) 新增零件的 16x16 矩阵记录追加进 perception_input/part_matrix.jsonl
#      （含 part_name 与 matrix 字段，schema_version=2）。
#   2) 运行 STEP177 的 body_part_sense_linker.py 生成对应身体感知记录。
#   3) 重新运行本脚本：body_parts 列表与报告文本会自动包含新部件，
#      无需修改本脚本逻辑。
# ----------------------------------------------------------------------
