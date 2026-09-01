#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP200 - luoshen_image_clustering.py
=================================================
洛神 200 图矩阵库相似度聚类模块：
1) 读取 perception_input/real_object_matrix_200.jsonl 全部记录；
2) 数据清洗：对每个 object 过滤掉全 0 / 全 255 的 matrix，剩余矩阵
   平均得到代表矩阵参与正常聚类；仅当全部 matrix 都被过滤时才将
   该 object 归入异常组（group_id 从 999 开始递减）；
3) 正常物体聚类：物体间相似度 sim = 1 - (逐像素平均绝对差 / 255)，
   采用贪心分组算法，阈值 SIM_THRESHOLD = 0.90；
   聚类完全由脚本运行时计算，代码中不预设任何分组归属；
4) 写 perception_input/object_clustering_200.jsonl
   （正常组 group_id 从 1 起递增，异常组从 999 起递减）；
5) 按 v2 公式追加 hash_chain_v2.log 一条。

算法说明（如何调整）：
- 聚类粒度：调大 SIM_THRESHOLD -> 组更多更细；调小 -> 组更少更粗。
- 每个 object 以其所有正常 matrix 的平均矩阵作为代表，物体间相似度
  即两个代表矩阵的相似度（sim = 1 - 平均绝对差 / 255）。
"""
import hashlib
import json
import time

SIZE = 16
SIM_THRESHOLD = 0.90

INPUT_FILE = "perception_input/real_object_matrix_200.jsonl"
OUTPUT_FILE = "perception_input/object_clustering_200.jsonl"
CHAIN_FILE = "hash_chain_v2.log"


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
        "{}{}{}".format(file_hash, prev_hash, str(ts)).encode("utf-8")).hexdigest()
    entry = {"schema_version": 2, "timestamp": ts, "file": target_file,
             "file_hash": file_hash, "prev_hash": prev_hash, "record_hash": record_hash}
    with open(chain_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def is_abnormal(matrix):
    # 全 0 或全 255 视为异常数据
    black = all(v == 0 for row in matrix for v in row)
    white = all(v == 255 for row in matrix for v in row)
    return black or white


def sim_between(m1, m2):
    # sim = 1 - (逐像素平均绝对差 / 255)
    total = 0
    for r in range(SIZE):
        for c in range(SIZE):
            total += abs(m1[r][c] - m2[r][c])
    return 1.0 - (total / 255.0 / (SIZE * SIZE))


def average_matrix(matrices):
    # 多个矩阵逐像素取整平均，作为 object 的代表矩阵
    n = len(matrices)
    out = [[0] * SIZE for _ in range(SIZE)]
    for m in matrices:
        for r in range(SIZE):
            for c in range(SIZE):
                out[r][c] += m[r][c]
    for r in range(SIZE):
        for c in range(SIZE):
            out[r][c] = int(round(out[r][c] / n))
    return out


def main():
    # 1) 读取全部记录，按物体名聚合矩阵列表
    objects = {}            # object -> [matrix, ...]
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            objects.setdefault(rec["object"], []).append(rec["matrix"])

    # 2) 数据清洗：过滤全 0/全 255 矩阵，剩余矩阵平均为代表矩阵；
    #    仅当全部矩阵被过滤时才归入异常组
    abnormal_objects = []
    reps = {}               # object -> 代表矩阵
    for obj, mats in objects.items():
        clean = [m for m in mats if not is_abnormal(m)]
        if clean:
            reps[obj] = average_matrix(clean)
        else:
            abnormal_objects.append(obj)

    # 3) 正常物体贪心聚类（基于代表矩阵）
    groups = []
    for obj in reps:
        placed = False
        for g in groups:
            # 与组内任意物体相似度 >= 阈值则加入该组
            for member in g:
                if sim_between(reps[obj], reps[member]) >= SIM_THRESHOLD:
                    g.append(obj)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            groups.append([obj])

    # 4) 生成聚类结果（正常组 1 起递增，异常组 999 起递减）
    ts = time.time()
    records = []
    for gid, g in enumerate(groups, start=1):
        records.append({
            "schema_version": 2, "timestamp": ts, "group_id": gid,
            "members": g, "source": "luoshen_image_clustering",
        })
    ab_id = 999
    for o in abnormal_objects:
        records.append({
            "schema_version": 2, "timestamp": ts, "group_id": ab_id,
            "members": [o], "source": "luoshen_image_clustering",
        })
        ab_id -= 1

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5) 控制台打印
    print("=== 正常组数量: %d ===" % len(groups))
    print("=== 异常组数量: %d ===" % len(abnormal_objects))
    for r in records:
        print("group %s: %s" % (r["group_id"], ",".join(r["members"])))

    # 6) 哈希链追加（仅一条）
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
