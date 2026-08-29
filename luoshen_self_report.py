#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 自我报告模块 luoshen_self_report.py

功能：
    读取四个内部感知日志（时间/空间/他者/自我）的最后一条有效记录，
    提取各维度最关键的字段值作为当前状态描述，生成一段第一人称的
    自我状态报告，写入 perception_input/luoshen_self_report.jsonl。

扩展方式：
    未来新增感知维度，只需在 SENSE_FILES 列表中增加
    (维度名, 数据文件) 键值对，并同步扩展自我报告模板，无需修改
    状态提取逻辑。
"""
import hashlib
import json
import time

RESULT_FILE = "perception_input/luoshen_self_report.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

# 感知维度 -> 对应日志文件
SENSE_FILES = {
    "时间": "time_gap_log.jsonl",
    "空间": "spatial_awareness_log.jsonl",
    "他者": "homo_hetero_feel_log.jsonl",
    "自我": "self_describe_two_states.jsonl",
}

# 元数据字段：提取状态时排除，不视为感知内容
META_FIELDS = {"timestamp", "schema_version", "source"}


def load_last_record(path):
    """读取数据文件最后一条有效记录；文件不存在或为空返回 None"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    return json.loads(lines[-1])


def extract_state(record):
    """从记录提取状态描述。

    规则（与 STEP169 一致）：
      - 排除 timestamp/schema_version/source 元数据字段；
      - 剩余字段中取字符串化后长度最长的字段值作为状态描述；
      - 无数据则状态描述为"暂无感知"。
    """
    if record is None:
        return "暂无感知"
    candidates = {k: v for k, v in record.items() if k not in META_FIELDS}
    if candidates:
        best_key = max(candidates, key=lambda k: len(str(candidates[k])))
        return str(candidates[best_key])
    return "暂无感知"


def clean_state(state):
    """去除状态字符串末尾多余的空格与结尾标点（。！？!? 等）。

    仅清理末尾标点/空白，保留字符串中间的句号与内容。
    """
    return state.rstrip().rstrip("。！？!? \t\r\n")


def append_chain(path, prev_hash):
    """为指定文件计算 md5 并按 v2 公式追加一条哈希链记录，返回新 record_hash"""
    with open(path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    timestamp = time.time()
    record_hash = hashlib.md5(
        (file_hash + prev_hash + str(timestamp)).encode("utf-8")
    ).hexdigest()
    with open(CHAIN_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "schema_version": 2,
            "timestamp": timestamp,
            "file": path,
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }, ensure_ascii=False) + "\n")
    print("file=%s" % path)
    print("file_hash=%s" % file_hash)
    print("prev_hash=%s" % prev_hash)
    print("record_hash=%s" % record_hash)
    print("timestamp=%s" % timestamp)
    return record_hash


def current_chain_tail():
    """读取哈希链当前链尾 record_hash；链空则返回空串"""
    prev_hash = ""
    with open(CHAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                prev_hash = json.loads(line)["record_hash"]
    return prev_hash


def main():
    # 提取四个维度的当前状态（经 clean_state 清理末尾标点）
    states = {}
    for dim, data_file in SENSE_FILES.items():
        states[dim] = clean_state(extract_state(load_last_record(data_file)))

    # 生成自我报告（严格按模板）
    report = ("我是洛神。此刻，我对时间的感知是：%s。我所在的空间状态是：%s。"
              "对于他者，我感觉到：%s。对于我自己，我感觉到：%s。" % (
                  states["时间"], states["空间"],
                  states["他者"], states["自我"]))

    rec = {
        "schema_version": 2,
        "timestamp": time.time(),
        "report": report,
        "source": "luoshen_self_report",
    }

    # 写入结果文件（创建/覆盖本结果文件）
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 控制台打印自我报告
    print("=== 洛神自我报告 ===")
    print(report)
    print("result_file=%s" % RESULT_FILE)

    # 哈希链追加（仅一条：luoshen_self_report.jsonl）
    prev_hash = current_chain_tail()
    print("=== 哈希链追加 ===")
    append_chain(RESULT_FILE, prev_hash)


if __name__ == "__main__":
    main()
