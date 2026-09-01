#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 简单汉字16x16模板匹配识别器（带去重记忆模块） simple_recognizer.py

扩展新字符说明：
    只需在 perception_input/simple_char_matrix.jsonl 中新增一条记录
    （含 char 与 16x16 matrix 字段），识别器加载模板时自动纳入，
    无需修改核心识别逻辑。

记忆模块说明：
    正确识别过的样本会写入 perception_input/recognition_memory.jsonl。
    写入前做两级约束：
      1) 去重：若记忆库已存在与待写入样本相似度 >= DEDUP_THRESHOLD(0.98)
         的记录，则跳过写入；
      2) 上限：每个字符记忆条数不超过 MAX_MEMORY_PER_CHAR，超出时删除
         该字符最早一条记忆后写入（通过重写 jsonl 完成）。
    识别时优先与记忆库匹配（命中阈值 MEMORY_HIT_THRESHOLD 0.99），
    未命中再走模板匹配。
"""
import hashlib
import json
import random
import time

TEMPLATE_FILE = "perception_input/simple_char_matrix.jsonl"
MEMORY_FILE = "perception_input/recognition_memory.jsonl"
RESULT_FILE = "perception_input/recognition_test_result.jsonl"
CHAIN_FILE = "hash_chain_v2.log"
NOISE_PIXELS = 3       # 每个测试样本随机翻转的像素数
SAMPLES_PER_CHAR = 10  # 每个汉字生成的带噪声样本数
RANDOM_SEED = 42       # 固定随机种子，保证可复现
MEMORY_HIT_THRESHOLD = 0.99   # 记忆命中判定阈值
DEDUP_THRESHOLD = 0.995      # 去重判定阈值（仅对完全相同/高度相似样本去重）
MAX_MEMORY_PER_CHAR = 10      # 每个字符记忆条数上限


def load_templates(path):
    """加载参考矩阵作为模板库：{char: matrix}"""
    templates = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            templates[rec["char"]] = rec["matrix"]
    return templates


def load_memory(path):
    """加载记忆库：返回 [(matrix, char), ...]；文件不存在或为空则返回 []"""
    memory = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                memory.append((rec["matrix"], rec["char"]))
    except FileNotFoundError:
        pass
    return memory


def add_noise(matrix, rng, n):
    """随机翻转 n 个像素（0<->255），返回副本"""
    h = len(matrix)
    w = len(matrix[0])
    cells = [(r, c) for r in range(h) for c in range(w)]
    pick = rng.sample(cells, n)
    noisy = [row[:] for row in matrix]
    for (r, c) in pick:
        noisy[r][c] = 0 if noisy[r][c] == 255 else 255
    return noisy


def match_score(a, b):
    """逐像素比较，返回相同像素比例（0.0 ~ 1.0）"""
    total = len(a) * len(a[0])
    same = sum(
        1
        for r in range(len(a))
        for c in range(len(a[0]))
        if a[r][c] == b[r][c]
    )
    return same / total


def append_memory(path, char, matrix):
    """去重 + 上限后写入一条记忆记录（必要时重写 jsonl）"""
    # 读取当前全部记忆记录
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except FileNotFoundError:
        pass

    # 去重：若已存在与待写入样本相似度 >= DEDUP_THRESHOLD 的同字符记录，则跳过
    for rec in records:
        if rec["char"] == char and match_score(rec["matrix"], matrix) >= DEDUP_THRESHOLD:
            return

    # 上限：该字符条数达到上限时，删除最早一条（按文件追加顺序）
    char_count = sum(1 for rec in records if rec["char"] == char)
    if char_count >= MAX_MEMORY_PER_CHAR:
        first_idx = None
        for idx, rec in enumerate(records):
            if rec["char"] == char:
                first_idx = idx
                break
        if first_idx is not None:
            del records[first_idx]

    # 追加新记录并重写文件
    rec = {
        "schema_version": 2,
        "timestamp": time.time(),
        "char": char,
        "matrix": matrix,
        "source": "recognition_memory",
    }
    records.append(rec)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def recognize(templates, memory, rng):
    """对全部样本做一次识别；返回记录列表（含 source）"""
    records = []
    for char, matrix in templates.items():
        for i in range(SAMPLES_PER_CHAR):
            noisy = add_noise(matrix, rng, NOISE_PIXELS)

            # 1) 先尝试记忆命中
            mem_best = None
            mem_best_score = -1.0
            for mem_matrix, mem_char in memory:
                s = match_score(noisy, mem_matrix)
                if s > mem_best_score:
                    mem_best_score = s
                    mem_best = mem_char
            if memory and mem_best_score >= MEMORY_HIT_THRESHOLD:
                predicted = mem_best
                score = mem_best_score
                source = "memory"
            else:
                # 2) 模板匹配兜底
                tmpl_best = None
                tmpl_best_score = -1.0
                for tmpl_char, tmpl in templates.items():
                    s = match_score(noisy, tmpl)
                    if s > tmpl_best_score:
                        tmpl_best_score = s
                        tmpl_best = tmpl_char
                predicted = tmpl_best
                score = tmpl_best_score
                source = "template"

            correct = (predicted == char)
            records.append({
                "char": char,
                "test_id": i + 1,
                "predicted": predicted,
                "correct": correct,
                "score": round(score, 4),
                "source": source,
            })

            # 3) 正确样本写入记忆（受去重与上限约束）
            if correct:
                append_memory(MEMORY_FILE, char, noisy)
    return records


def append_chain(path, prev_hash):
    """为指定文件计算 md5 并追加一条 v2 哈希链记录，返回新 record_hash"""
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
    prev_hash = ""
    with open(CHAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                prev_hash = json.loads(line)["record_hash"]
    return prev_hash


def main():
    templates = load_templates(TEMPLATE_FILE)

    # ===== 阶段A：清空记忆文件，记忆库为空，全走模板匹配 =====
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        pass
    rng_a = random.Random(RANDOM_SEED)
    records_a = recognize(templates, [], rng_a)

    # ===== 阶段B：记忆库已含阶段A记录，应全部记忆命中 =====
    memory = load_memory(MEMORY_FILE)
    rng_b = random.Random(RANDOM_SEED)
    records_b = recognize(templates, memory, rng_b)

    # ===== 阶段B结果写入 jsonl（覆盖，含 source 字段） =====
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        for rec in records_b:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ===== 任务完成后追加哈希链：记忆文件 + 识别结果文件 =====
    prev_hash = current_chain_tail()
    print("=== 哈希链追加 ===")
    print("--- recognition_memory.jsonl ---")
    prev_hash = append_chain(MEMORY_FILE, prev_hash)
    print("--- recognition_test_result.jsonl ---")
    append_chain(RESULT_FILE, prev_hash)

    # ===== 输出摘要 =====
    print("=== 模板库 ===")
    for ch in templates:
        print("template: %s" % ch)
    print("=== 阶段A（记忆库为空，全部模板匹配）===")
    ca = sum(1 for r in records_a if r["correct"])
    print("correct=%d/%d accuracy=%.4f" % (ca, len(records_a), ca / len(records_a)))
    print("=== 阶段B（含记忆库）每个测试样本的预测结果 ===")
    for rec in records_b:
        print("char=%s test_id=%d predicted=%s correct=%s score=%.4f source=%s" % (
            rec["char"], rec["test_id"], rec["predicted"],
            rec["correct"], rec["score"], rec["source"]))
    cb = sum(1 for r in records_b if r["correct"])
    n_mem = sum(1 for r in records_b if r["source"] == "memory")
    n_tpl = sum(1 for r in records_b if r["source"] == "template")
    print("=== 阶段B最终准确率 ===")
    print("correct=%d/%d accuracy=%.4f" % (cb, len(records_b), cb / len(records_b)))
    print("source=memory 样本数: %d" % n_mem)
    print("source=template 样本数: %d" % n_tpl)

    # 记忆文件最终统计
    mem_records = []
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                mem_records.append(json.loads(line))
    print("=== 记忆文件最终统计 ===")
    print("memory_total=%d" % len(mem_records))
    per_char = {}
    for rec in mem_records:
        per_char[rec["char"]] = per_char.get(rec["char"], 0) + 1
    print("per_char=%s" % json.dumps(per_char, ensure_ascii=False))


if __name__ == "__main__":
    main()
