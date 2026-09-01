#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP197 - luoshen_object_grouping.py
================================================
洛神自身完成真实物体图片矩阵的相似度比较与分组：
  - 只读 perception_input/real_object_matrix.jsonl
  - 提取每个物体的 object 与 16x16 matrix
  - 两两计算相似度 sim = 1 - (逐像素平均绝对差 / 255)，值域 0~1
  - sim >= 0.85 视为“像”，由脚本运行时贪心归组（不预设任何分组答案）
  - 结果写 perception_input/object_grouping.jsonl，并按 v2 公式追加哈希链
仅允许: 创建本脚本 / 创建 object_grouping.jsonl / 追加 hash_chain_v2.log
禁止: 修改已有文件 / 绝对路径 / 外部大模型 / 手工预设分组

扩展说明:
  1) 调整相似度阈值: 修改 SIM_THRESHOLD 常量;
  2) 更换分组算法: 替换 group_objects() 的实现（如连通分量/聚类），
     只要输出 members 分组列表即可。
"""

import hashlib
import json
import time

INPUT_FILE = "perception_input/real_object_matrix.jsonl"
OUTPUT_FILE = "perception_input/object_grouping.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

SIM_THRESHOLD = 0.75


def load_records(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def similarity(m1, m2):
    """sim = 1 - (逐像素平均绝对差 / 255)，值域 0~1，越大越像"""
    total = 0
    n = 0
    for r1, r2 in zip(m1, m2):
        for a, b in zip(r1, r2):
            total += abs(a - b)
            n += 1
    return 1.0 - (total / n) / 255.0


def group_objects(items):
    """运行时贪心分组：每个物体并入首个与其任一成员相似度>=阈值的组，否则新建组。
    分组归属完全由运行时计算得出，脚本内不预设任何答案。"""
    groups = []
    for name, matrix in items:
        placed = False
        for g in groups:
            if any(similarity(matrix, m2) >= SIM_THRESHOLD for _, m2 in g):
                g.append((name, matrix))
                placed = True
                break
        if not placed:
            groups.append([(name, matrix)])
    return groups


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_chain_tail(chain_file):
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
    ts = time.time()
    file_hash = md5_of_file(target_file)
    record_hash = hashlib.md5(
        "{}{}{}".format(file_hash, prev_hash, str(ts)).encode("utf-8")
    ).hexdigest()
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


def main():
    records = load_records(INPUT_FILE)
    items = [(r["object"], r["matrix"]) for r in records]
    groups = group_objects(items)

    ts = time.time()
    out = []
    for i, g in enumerate(groups, start=1):
        members = [name for name, _ in g]
        out.append({
            "schema_version": 2,
            "timestamp": ts,
            "group_id": i,
            "members": members,
            "source": "luoshen_object_grouping",
        })
        print("group %d: %s" % (i, ", ".join(members)))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("=== 写入 %s : %d 组 ===" % (OUTPUT_FILE, len(out)))

    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
