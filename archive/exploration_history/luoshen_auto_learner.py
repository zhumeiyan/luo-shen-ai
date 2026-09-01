#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP212: luoshen_auto_learner.py
洛神自动学习迭代器：采样 -> 变异 -> 评估 -> 保留 的自循环。
本次运行 10 轮，验证自主学习可行性。

依赖：hashlib、json、time、random
只读数据：
  - perception_input/luoshen_unified_lexicon.jsonl
  - perception_input/hanzi_matrix_llm_batch1.jsonl
  - perception_input/llm_teaching_batch1.jsonl
产出：
  - perception_input/luoshen_auto_learning_log.jsonl (每轮1条 + 末尾最终保留列表1条)
上链：追加 hash_chain_v2.log 一条（v2 公式）

参数可调：
  - POP_SIZE     种群规模（默认 50）
  - KEEP         每轮保留个体数（默认 25，应 <= POP_SIZE）
  - ROUNDS       迭代轮数（默认 10）
  - MIN_FLIP     单个体最小变异像素数（默认 1）
  - MAX_FLIP     单个体最大变异像素数（默认 3）
"""
import hashlib
import json
import time
import random

MATRIX_SRC = "perception_input/hanzi_matrix_llm_batch1.jsonl"
LEXICON_SRC = "perception_input/luoshen_unified_lexicon.jsonl"
TEACHING_SRC = "perception_input/llm_teaching_batch1.jsonl"
OUT = "perception_input/luoshen_auto_learning_log.jsonl"
CHAIN = "hash_chain_v2.log"
SOURCE = "luoshen_auto_learner"
SCHEMA = 2

POP_SIZE = 50
KEEP = 25
ROUNDS = 10
MIN_FLIP = 1
MAX_FLIP = 3


def md5hex(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def load_lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f.read().strip().splitlines()]


def load_original_matrices():
    """原始库：char -> [matrix,...]（hanzi_matrix_llm_batch1 每字一条）"""
    ref = {}
    for r in load_lines(MATRIX_SRC):
        ref.setdefault(r["char"], []).append(r["matrix"])
    return ref


def load_lexicon_tags():
    """联合词库：char -> tags（luoshen_unified_lexicon.jsonl）"""
    tags_map = {}
    for r in load_lines(LEXICON_SRC):
        if r.get("char") and r.get("tags"):
            tags_map[r["char"]] = list(r["tags"])
    return tags_map


def load_global_tags():
    """全局 tag 集合：llm_teaching_batch1.jsonl 所有 hanzi 记录的 tags"""
    gtags = set()
    for r in load_lines(TEACHING_SRC):
        if r.get("type") == "hanzi" and r.get("content"):
            for t in r["content"].get("tags", []):
                gtags.add(t)
    return gtags


def mean_abs_diff(m1, m2):
    n = sum(
        abs(a - b)
        for row_a, row_b in zip(m1, m2)
        for a, b in zip(row_a, row_b)
    )
    total = len(m1) * len(m1[0])
    return n / total


def similarity(m, ref_matrices):
    """sim = 1 - (平均绝对差 / 255)；多原始矩阵取平均"""
    if not ref_matrices:
        return None
    d = sum(mean_abs_diff(m, ref) for ref in ref_matrices) / len(ref_matrices)
    return 1.0 - d / 255.0


def is_uniform(m):
    """全 0 或全 255 视为无效"""
    vals = set(v for row in m for v in row)
    return vals in ({0}, {255})


def mutate_matrix(m):
    """随机翻转 1~3 个像素（0<->255）"""
    out = [row[:] for row in m]
    h, w = len(out), len(out[0])
    cells = [(i, j) for i in range(h) for j in range(w)]
    k = random.randint(MIN_FLIP, MAX_FLIP)
    for i, j in random.sample(cells, k):
        out[i][j] = 0 if out[i][j] == 255 else 255
    return out


def mutate_tags(tags, gtags, rng):
    """含 tags 个体：随机删一个原有 tag，或从全局 tag 集合随机加一个"""
    if not tags:
        return tags
    if rng.random() < 0.5 and len(tags) > 1:
        out = tags[:]
        out.pop(rng.randrange(len(out)))
        return out
    pool = [t for t in gtags if t not in tags]
    if pool:
        return tags + [rng.choice(pool)]
    return tags


def mutate(individual, tags_map, gtags, rng):
    """对个体做一次变异：像素翻转 + tags 调整"""
    m = mutate_matrix(individual["matrix"])
    tags = mutate_tags(individual.get("tags", []), gtags, rng)
    return {"char": individual["char"], "matrix": m, "tags": tags}


def fitness_of(m, ref_matrices):
    """变异后个体适应度：变异后 sim >= 原 sim(1.0) 且非全同色才用变异后，否则 原sim-0.01"""
    base = similarity(m, ref_matrices)
    if base is None:
        return 0.0
    sim = similarity(m, ref_matrices)
    if sim >= base and not is_uniform(m):
        return sim
    return base - 0.01


def main():
    rng = random.Random(20260829)
    ref = load_original_matrices()
    tags_map = load_lexicon_tags()
    gtags = load_global_tags()

    # 1. 初始种群：优先联合词库，不足 50 时用 hanzi_matrix_llm_batch1 前 50
    init = []
    for r in load_lines(LEXICON_SRC):
        if r.get("char") and r.get("matrix"):
            init.append({"char": r["char"], "matrix": r["matrix"], "tags": r.get("tags", [])})
    if len(init) < POP_SIZE:
        for r in load_lines(MATRIX_SRC):
            if r["char"] not in {x["char"] for x in init}:
                init.append({"char": r["char"], "matrix": r["matrix"], "tags": []})
            if len(init) >= POP_SIZE:
                break
    population = init[:POP_SIZE]

    log_lines = []

    for rnd in range(1, ROUNDS + 1):
        # 2. 变异
        mutants = []
        for ind in population:
            mu = mutate(ind, tags_map, gtags, rng)
            mu["fitness"] = fitness_of(mu["matrix"], ref.get(mu["char"], []))
            mutants.append(mu)

        # 3. 排序选择
        mutants.sort(key=lambda x: x["fitness"], reverse=True)
        kept = mutants[:KEEP]

        # 4. 恢复种群规模（复制一份）
        population = kept + [dict(x) for x in kept]
        population = population[:POP_SIZE]

        best = kept[0]
        rec = {
            "schema_version": SCHEMA,
            "timestamp": time.time(),
            "round": rnd,
            "best_char": best["char"],
            "best_similarity": round(best["fitness"], 6),
            "population_size": POP_SIZE,
            "source": SOURCE,
        }
        log_lines.append(rec)
        print("[STEP212] round %d best_char=%s best_similarity=%.6f" % (rnd, best["char"], best["fitness"]))

    # 最终保留 25 个 char 列表
    final_rec = {
        "schema_version": SCHEMA,
        "timestamp": time.time(),
        "round": ROUNDS + 1,
        "final_chars": [x["char"] for x in population[:KEEP]],
        "population_size": POP_SIZE,
        "source": SOURCE,
    }
    log_lines.append(final_rec)

    with open(OUT, "w", encoding="utf-8") as f:
        for rec in log_lines:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(OUT, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    print("[STEP212] written", OUT)
    print("[STEP212] records =", len(log_lines))
    print("[STEP212] file_md5 =", file_hash)

    # 5. 哈希链追加（仅一条）
    lines = open(CHAIN, encoding="utf-8").read().strip().splitlines()
    prev_hash = json.loads(lines[-1])["record_hash"]
    ts = time.time()
    record_hash = md5hex(file_hash + prev_hash + str(ts))
    entry = {
        "schema_version": SCHEMA,
        "timestamp": ts,
        "file": OUT,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("[STEP212] prev_hash =", prev_hash)
    print("[STEP212] record_hash =", record_hash)


if __name__ == "__main__":
    main()
