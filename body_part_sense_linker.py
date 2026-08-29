#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP177 - body_part_sense_linker.py
=============================================
洛神身体部件感知连接模块：将已识别的硬件零件矩阵(part_matrix.jsonl)
与空间感知数据(spatial_awareness_log.jsonl)关联，生成"身体部件感知"记录。

依赖: hashlib, json, time
仅允许:
  - 读取 perception_input/part_matrix.jsonl（只读）
  - 读取 spatial_awareness_log.jsonl（只读）
  - 写入 perception_input/body_part_sense.jsonl（新建）
  - 追加 hash_chain_v2.log（哈希链，仅追加一条）
禁止: 修改任何已有文件 / 绝对路径 / 外部大模型
"""

import hashlib
import json
import time

# ----------------------------------------------------------------------
# 路径（相对当前工作目录，禁止绝对路径）
# ----------------------------------------------------------------------
MATRIX_FILE = "perception_input/part_matrix.jsonl"
SPATIAL_FILE = "spatial_awareness_log.jsonl"
OUTPUT_FILE = "perception_input/body_part_sense.jsonl"
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


def load_part_matrix(path):
    """读取零件矩阵文件，返回记录列表。"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_spatial_sense(path):
    """
    读取空间感知日志的最后一条有效记录。
    排除元数据字段(timestamp/schema_version/source)后，
    取字符串化后长度最长的字段值作为空间状态描述。
    """
    last = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    if last is None:
        raise RuntimeError("spatial_awareness_log.jsonl 无有效记录")

    best_value = ""
    for key, value in last.items():
        if key in META_FIELDS:
            continue
        text = str(value)
        if len(text) > len(best_value):
            best_value = text
    return best_value


def count_zeros_255(matrix):
    """统计矩阵中 0 元素与 255 元素的数量。"""
    zeros = 0
    two_five_five = 0
    for row in matrix:
        for val in row:
            if val == 0:
                zeros += 1
            elif val == 255:
                two_five_five += 1
    return zeros, two_five_five


def build_sense_records(parts, spatial_desc):
    """
    为每个零件生成一条身体部件感知记录。
    模板:
      body_part_sense = "洛神对{零件名}的身体感知：看到{零件名}的轮廓矩阵；同时空间感知显示：{空间状态描述}"
      part_matrix_summary = "16x16矩阵，0元素数量=X，255元素数量=Y"
    """
    records = []
    for part in parts:
        name = part["part_name"]
        zeros, two_five_five = count_zeros_255(part["matrix"])
        summary = "16x16矩阵，0元素数量={}，255元素数量={}".format(zeros, two_five_five)
        record = {
            "schema_version": 2,
            "timestamp": time.time(),
            "part_name": name,
            "part_matrix_summary": summary,
            "spatial_sense": spatial_desc,
            "body_part_sense": "洛神对{}的身体感知：看到{}的轮廓矩阵；同时空间感知显示：{}".format(
                name, name, spatial_desc
            ),
        }
        records.append(record)
    return records


def append_hash_chain(chain_file, target_file, prev_hash):
    """
    按哈希链 v2 公式追加一条记录：
      record_hash = md5(file_hash + prev_hash + str(timestamp))
    只追加这一条。
    """
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
    """读取哈希链最后一条记录，返回其 record_hash。"""
    tail = None
    with open(chain_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tail = json.loads(line)
    if tail is None:
        raise RuntimeError("hash_chain_v2.log 无记录，无法取得链尾")
    return tail["record_hash"]


def main():
    # 1. 读取零件矩阵（预期 5 条）
    parts = load_part_matrix(MATRIX_FILE)

    # 2. 读取空间状态描述（取最后一条非元数据最长字符串字段）
    spatial_desc = load_spatial_sense(SPATIAL_FILE)

    # 3/4. 生成记录并写入 body_part_sense.jsonl
    records = build_sense_records(parts, spatial_desc)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 5. 控制台打印 5 条记录
    for rec in records:
        print(json.dumps(rec, ensure_ascii=False))

    # 6. 哈希链追加一条
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)

    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# 如何扩展新零件：
#   1) 将新零件的 16x16 矩阵记录追加进 perception_input/part_matrix.jsonl
#      （record 需含 part_name 与 matrix 字段，schema_version=2）。
#   2) 重新运行本脚本：build_sense_records 会自动为每个零件生成一条
#      body_part_sense 记录，并追加哈希链。无需修改本脚本逻辑。
# ----------------------------------------------------------------------
