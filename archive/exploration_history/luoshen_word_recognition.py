#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP203 - luoshen_word_recognition.py
=================================================
验证洛神能否使用词原型矩阵识别图片矩阵：
1) 读取 word_prototype_matrix.jsonl，建立 word -> prototype_matrix 映射；
2) 读取 real_object_matrix_200.jsonl，均匀抽取 10 条测试样本
   （优先不同 object，覆盖不同类别；不足 10 个 object 时按出现顺序取前 10 条）；
3) 对每条测试样本，与每个词原型计算相似度
   sim = 1 - (逐像素平均绝对差 / 255)，取最高的前 3 个词；
4) 写 perception_input/word_recognition_test.jsonl（10 条）；
5) 按 v2 公式追加 hash_chain_v2.log 一条。

扩展与调整（如何修改）：
- 测试样本量：修改 SAMPLE_COUNT 即可调整抽取条数。
- 识别阈值：修改 TOP_K 可调整返回的词个数；若需要门限过滤，
  可在取 top 前先剔除 sim 低于某阈值的词。
"""
import hashlib
import json
import time

SIZE = 16
SAMPLE_COUNT = 10
TOP_K = 3

PROTO_FILE = "perception_input/word_prototype_matrix.jsonl"
MATRIX_FILE = "perception_input/real_object_matrix_200.jsonl"
OUTPUT_FILE = "perception_input/word_recognition_test.jsonl"
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


def sim_between(m1, m2):
    # sim = 1 - (逐像素平均绝对差 / 255)
    total = 0
    for r in range(SIZE):
        for c in range(SIZE):
            total += abs(m1[r][c] - m2[r][c])
    avg_abs_diff = total / (SIZE * SIZE)
    return 1.0 - avg_abs_diff / 255.0


def sample_records(records, count):
    # 优先不同 object，按出现顺序取；不足则按出现顺序补足 count 条
    seen = set()
    picked = []
    for rec in records:
        obj = rec["object"]
        if obj not in seen:
            seen.add(obj)
            picked.append(rec)
        if len(picked) == count:
            break
    if len(picked) < count:
        for rec in records:
            if len(picked) == count:
                break
            if rec not in picked:
                picked.append(rec)
    return picked


def main():
    # 1) word -> prototype_matrix
    prototypes = {}
    with open(PROTO_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            prototypes[rec["word"]] = rec["prototype_matrix"]

    # 2) 读取真实物体矩阵并抽样 10 条
    records = []
    with open(MATRIX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    samples = sample_records(records, SAMPLE_COUNT)

    # 3) 每条样本与各词原型算相似度，取 top3
    ts = time.time()
    results = []
    for rec in samples:
        m = rec["matrix"]
        scored = []
        for word, proto in prototypes.items():
            scored.append((sim_between(m, proto), word))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:TOP_K]
        top_words = [w for _, w in top]
        top_scores = [round(s, 6) for s, _ in top]
        results.append({
            "schema_version": 2, "timestamp": ts, "object": rec["object"],
            "top_words": top_words, "top_scores": top_scores,
            "source": "luoshen_word_recognition",
        })

    # 4) 写输出文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 5) 控制台打印每条记录
    for r in results:
        print(json.dumps(r, ensure_ascii=False))

    # 6) 哈希链追加（仅一条）
    prev_hash = read_chain_tail(CHAIN_FILE)
    entry = append_hash_chain(CHAIN_FILE, OUTPUT_FILE, prev_hash)
    print("--- hash_chain appended ---")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
