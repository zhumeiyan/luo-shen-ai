#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP201 - luoshen_group_impression.py
=================================================
根据真实图片聚类结果，为每个正常聚类组生成"组印象词"：
1) 读取 object_clustering_200.jsonl，取正常组（group_id < 999）；
2) 读取 real_object_matrix_200.jsonl，建立 object -> adjectives 映射；
3) 对每个正常组统计组内所有 object 的形容词出现次数，取前 TOP_K 个
   作为 group_impression（不足 TOP_K 个则用实际数量）；
4) 写 perception_input/group_impression_200.jsonl（每正常组一条）；
5) 按 v2 公式追加 hash_chain_v2.log 一条。

统计方式（如何调整）：
- 取词数量：修改 TOP_K（当前为 3）。
- 并列排序：Counter.most_common 按首次出现顺序稳定输出。
"""
import hashlib
import json
import time
from collections import Counter

TOP_K = 3

CLUSTER_FILE = "perception_input/object_clustering_200.jsonl"
MATRIX_FILE = "perception_input/real_object_matrix_200.jsonl"
OUTPUT_FILE = "perception_input/group_impression_200.jsonl"
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


def main():
    # 1) 读取聚类结果中的正常组（group_id < 999，忽略异常组）
    groups = []
    with open(CLUSTER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["group_id"] < 999:
                groups.append(rec)

    # 2) 建立 object -> adjectives 映射（同一 object 多次出现时取首次）
    obj_adj = {}
    with open(MATRIX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            obj_adj.setdefault(rec["object"], rec["adjectives"])

    # 3) 每组成印象词：统计组内形容词出现次数，取前 TOP_K 个
    ts = time.time()
    records = []
    for g in groups:
        cnt = Counter()
        for member in g["members"]:
            for adj in obj_adj.get(member, []):
                cnt[adj] += 1
        impression = [w for w, _ in cnt.most_common(TOP_K)]
        records.append({
            "schema_version": 2, "timestamp": ts, "group_id": g["group_id"],
            "members": g["members"], "group_impression": impression,
            "source": "luoshen_group_impression",
        })

    # 4) 写输出文件（每正常组一条）
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5) 控制台打印每条记录
    for r in records:
        print(json.dumps(r, ensure_ascii=False))

    # 6) 哈希链追加（仅一条）
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
