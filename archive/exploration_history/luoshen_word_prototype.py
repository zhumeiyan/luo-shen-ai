#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP202 - luoshen_word_prototype.py
=================================================
为每个组印象词建立 16x16 原型矩阵：
1) 读取 group_impression_200.jsonl，收集每个正常组的 group_impression；
2) 读取 real_object_matrix_200.jsonl，建立 object -> 矩阵列表 映射；
3) 读取 object_clustering_200.jsonl，建立 group_id -> members 映射；
4) 对每个印象词：收集包含该词的所有组的成员物体矩阵，过滤全 0/全 255
   异常矩阵，对剩余矩阵逐像素取整平均，得到该词的原型矩阵；
5) 找不到任何正常矩阵的词跳过，不生成原型；
6) 写 perception_input/word_prototype_matrix.jsonl（每词一条）；
7) 按 v2 公式追加 hash_chain_v2.log 一条。

扩展与调整（如何修改）：
- 新增词的抽象原型：把新词与某个已有原型比对相似度即可扩展，无需改本脚本。
- 平均方法：当前为逐像素取整平均；若想加权，可修改 collect 与平均逻辑。
"""
import hashlib
import json
import time

SIZE = 16

IMPRESSION_FILE = "perception_input/group_impression_200.jsonl"
MATRIX_FILE = "perception_input/real_object_matrix_200.jsonl"
CLUSTER_FILE = "perception_input/object_clustering_200.jsonl"
OUTPUT_FILE = "perception_input/word_prototype_matrix.jsonl"
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
    # 全 0 或全 255 视为异常矩阵
    black = all(v == 0 for row in matrix for v in row)
    white = all(v == 255 for row in matrix for v in row)
    return black or white


def average_matrices(matrices):
    # 逐像素取整平均；矩阵元素保证 0~255
    n = len(matrices)
    out = [[0] * SIZE for _ in range(SIZE)]
    for m in matrices:
        for r in range(SIZE):
            for c in range(SIZE):
                out[r][c] += m[r][c]
    for r in range(SIZE):
        for c in range(SIZE):
            v = int(round(out[r][c] / n))
            out[r][c] = max(0, min(255, v))
    return out


def main():
    # 1) 读取组印象：group_id -> impression 词列表
    group_impression = {}
    with open(IMPRESSION_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["group_id"] < 999:
                group_impression[rec["group_id"]] = rec["group_impression"]

    # 2) object -> 矩阵列表
    obj_matrices = {}
    with open(MATRIX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            obj_matrices.setdefault(rec["object"], []).append(rec["matrix"])

    # 3) group_id -> members
    group_members = {}
    with open(CLUSTER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["group_id"] < 999:
                group_members[rec["group_id"]] = rec["members"]

    # 4) 为每个印象词收集关联矩阵并求平均原型
    words = {}
    for gid, imp in group_impression.items():
        for w in imp:
            words.setdefault(w, []).append(gid)

    ts = time.time()
    records = []
    for w, gids in words.items():
        matrices = []
        for gid in gids:
            for member in group_members.get(gid, []):
                matrices.extend(obj_matrices.get(member, []))
        clean = [m for m in matrices if not is_abnormal(m)]
        if not clean:
            continue  # 无正常矩阵，跳过该词
        proto = average_matrices(clean)
        records.append({
            "schema_version": 2, "timestamp": ts, "word": w,
            "prototype_matrix": proto, "source": "luoshen_word_prototype",
        })

    # 5) 写输出文件（每词一条）
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 6) 控制台打印每个词及原型矩阵摘要
    for r in records:
        m = r["prototype_matrix"]
        flat = [v for row in m for v in row]
        nonzero = sum(1 for v in flat if v != 0)
        avg = sum(flat) / len(flat)
        print("%s: %dx%d nonzero=%d/%d avg=%.2f row0=%s" % (
            r["word"], SIZE, SIZE, nonzero, len(flat), avg, m[0]))

    # 7) 哈希链追加（仅一条）
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
