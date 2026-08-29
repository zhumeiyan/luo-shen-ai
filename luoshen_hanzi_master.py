#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP212-REV2: luoshen_hanzi_master.py
洛神汉字自主学习系统：洛神自己采样 -> 变异 -> 检验 -> 保留，覆盖更多汉字，并将学会的字持久化。

依赖：hashlib、json、time、random
只读数据（均为相对路径）：
  - perception_input/hanzi_matrix_llm_batch1.jsonl
  - perception_input/luoshen_unified_lexicon.jsonl
  - perception_input/llm_teaching_batch1.jsonl
  - perception_input/simple_char_matrix.jsonl
  - perception_input/hanzi_visual_map.jsonl
  - perception_input/hanzi_visual_map_batch2.jsonl
产出：
  - perception_input/hanzi_master_learned.jsonl（新学会的字每条一行持久化，同字只写第一次）
上链：追加 hash_chain_v2.log 一条（v2 公式，针对 hanzi_master_learned.jsonl）

可调参数：
  - TARGETS         每轮学习目标字数（默认 20）
  - MAX_ROUNDS      最大轮数（默认 100）
  - LEARN_GOAL      停止条件：累计学会新字数（默认 200）
  - MIN_FLIP/MAX_FLIP  变异强度（默认 1~5 像素）
  - MAX_CANDS       每个目标字生成的候选矩阵数（默认 8）
  - SIM_THRESH      识别通过阈值（候选与目标字参考的相似度下限，默认 0.82）
  - CONFUSE_THRESH  多样性门槛：候选与其它已学字的最大相似度上限，超出判混淆不保留（默认 0.93）
  - MAX_MAT_PER_CHAR 单个字最多保留矩阵数（默认 10，超出删相似度最低）

学习机制：
  1. 洛神汉字库：合并所有矩阵文件，char -> [matrix,...]；tags 从教学记录/联合词库补充。
  2. 待学汉字表：收集 llm_teaching_batch1.jsonl 所有记录 content 中出现的汉字（含拼音与 tags 尽量保留）。
  3. 每轮从未学会字中随机抽 TARGETS 个目标字。
  4. 生成候选矩阵：
     a. 部件拼接：若目标字可由两个已学字的矩阵左右拼接表示（字符串 A+B 或 B+A 等于目标字），
        则用左字矩阵左半区、右字矩阵右半区拼出初始候选；
     b. 否则取与目标字最相近的已学字矩阵（按字符编码距离最近，纯字符启发，不造字）做底，随机变异。
  5. 变异：对初始候选随机翻转 1~5 个像素，复制出 MAX_CANDS 个候选。
  6. 检验：候选与目标字参考（库中同字矩阵如有则取，否则以初始候选为参考）比相似度
     sim = 1 - mean_abs_diff/255；须同时满足：
     - 与目标字参考相似度 >= SIM_THRESH；
     - 与库中任何其它字的最大相似度 < CONFUSE_THRESH（否则与已有字混淆，不保留）；
     - 非全 0 / 全 255。
     取通过检验且相似度最高的候选为该目标字的学会字形。
  7. 保留：学会的字加入洛神汉字库；本轮记录写日志。
  8. 多样性约束：每轮结束，单个字矩阵数 > MAX_MAT_PER_CHAR 时删相似度最低的多余矩阵。
  9. 停止：累计学会新字 >= LEARN_GOAL，或达到 MAX_ROUNDS。
"""
import hashlib
import json
import time
import random

MATRIX_FILES = [
    ("perception_input/simple_char_matrix.jsonl", "char"),
    ("perception_input/hanzi_visual_map.jsonl", "hanzi"),
    ("perception_input/hanzi_visual_map_batch2.jsonl", "hanzi"),
    ("perception_input/luoshen_unified_lexicon.jsonl", "char"),
    ("perception_input/hanzi_matrix_llm_batch1.jsonl", "char"),
]
TEACHING_SRC = "perception_input/llm_teaching_batch1.jsonl"
LEARNED_OUT = "perception_input/hanzi_master_learned.jsonl"
CHAIN = "hash_chain_v2.log"
SOURCE = "luoshen_hanzi_master_learned"
SCHEMA = 2

TARGETS = 20
MAX_ROUNDS = 100
LEARN_GOAL = 200
MIN_FLIP = 1
MAX_FLIP = 5
MAX_CANDS = 8
SIM_THRESH = 0.82
CONFUSE_THRESH = 0.93
MAX_MAT_PER_CHAR = 10


def md5hex(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def load_lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f.read().strip().splitlines()]


def is_hanzi(ch):
    return len(ch) == 1 and "\u4e00" <= ch <= "\u9fff"


def build_library():
    """合并所有矩阵文件：char -> {matrices:[...], tags:[...]}"""
    lib = {}
    for path, ck in MATRIX_FILES:
        for r in load_lines(path):
            ch = r.get(ck)
            if isinstance(ch, str):
                ch = ch.strip()
            if not is_hanzi(ch):
                continue
            m = r.get("matrix")
            if not m:
                continue
            ent = lib.setdefault(ch, {"matrices": [], "tags": []})
            ent["matrices"].append(m)
            if r.get("tags"):
                ent["tags"] = list(dict.fromkeys(ent["tags"] + r["tags"]))
    # 从联合词库补充 tags
    try:
        for r in load_lines("perception_input/luoshen_unified_lexicon.jsonl"):
            ch = r.get("char")
            if ch and is_hanzi(ch) and r.get("tags") and ch in lib:
                lib[ch]["tags"] = list(dict.fromkeys(lib[ch]["tags"] + r["tags"]))
    except Exception:
        pass
    return lib


def build_teach_table():
    """待学汉字表：收集 llm_teaching_batch1 所有记录 content 中出现的汉字，尽量保留拼音与tags"""
    teach = {}
    for r in load_lines(TEACHING_SRC):
        c = r.get("content") or {}
        for k, v in c.items():
            if not isinstance(v, str):
                continue
            for ch in v:
                if is_hanzi(ch):
                    ent = teach.setdefault(ch, {"pinyin": None, "tags": []})
                    if c.get("pinyin") and isinstance(c.get("pinyin"), str):
                        ent["pinyin"] = c["pinyin"]
                    if c.get("tags"):
                        ent["tags"] = list(dict.fromkeys(ent["tags"] + c["tags"]))
    return teach


def mean_abs_diff(m1, m2):
    n = 0
    for row_a, row_b in zip(m1, m2):
        for a, b in zip(row_a, row_b):
            n += abs(a - b)
    total = len(m1) * len(m1[0])
    return n / total


def sim(m1, m2):
    return 1.0 - mean_abs_diff(m1, m2) / 255.0


def is_uniform(m):
    vals = set(v for row in m for v in row)
    return vals in ({0}, {255})


def mutate_matrix(m, rng, flips=None):
    """随机翻转像素（0<->255）。默认 1~5 像素（候选细化）；flips 可指定范围（初始候选造形）"""
    out = [row[:] for row in m]
    h, w = len(out), len(out[0])
    cells = [(i, j) for i in range(h) for j in range(w)]
    lo, hi = flips if flips else (MIN_FLIP, MAX_FLIP)
    k = rng.randint(lo, hi)
    for i, j in rng.sample(cells, k):
        out[i][j] = 0 if out[i][j] == 255 else 255
    return out


def concat_lr(mA, mB):
    """左右拼接：A 左半区、B 右半区"""
    h = len(mA)
    w = len(mA[0])
    half = w // 2
    return [rowA[:half] + rowB[half:] for rowA, rowB in zip(mA, mB)]


def max_sim_to_others(cand, lib, skip_ch=None):
    """候选与库中其它字（可跳过某字）的最大相似度"""
    worst = 0.0
    for ch, ent in lib.items():
        if skip_ch is not None and ch == skip_ch:
            continue
        for m in ent["matrices"]:
            s = sim(cand, m)
            if s > worst:
                worst = s
    return worst


def gen_concat_candidate(target, lib, rng):
    """部件拼接：目标字包含已学字 A（或 B）作部件时，用 A、B 矩阵左右拼接。
    返回 (matrix, method) 或 (None, None)"""
    learned = sorted(lib.keys())
    parts = [ch for ch in learned if ch != target and ch in target]
    if len(parts) >= 2:
        A, B = parts[0], parts[1]
        mA = lib[A]["matrices"][0]
        mB = lib[B]["matrices"][0]
        return concat_lr(mA, mB), "concat"
    if parts:
        # 单个部件：部件矩阵 + 邻近字矩阵拼右半，制造左右结构
        A = parts[0]
        mA = lib[A]["matrices"][0]
        base = min((ch for ch in learned if ch != A), key=lambda ch: abs(ord(target) - ord(ch)))
        mB = lib[base]["matrices"][0]
        return concat_lr(mA, mB), "concat"
    return None, None


def gen_variant_candidate(target, lib, rng):
    """相似字变异：取字符编码距离最近的已学字做底，大幅翻转制造新字形。
    若与已有字仍混淆则换下一邻近字重试。返回 (matrix, method) 或 (None, None)"""
    learned = sorted(lib.keys(), key=lambda ch: abs(ord(target) - ord(ch)))
    for ch in learned:
        if ch == target:
            continue
        base = lib[ch]["matrices"][0]
        for _ in range(24):
            # 初始候选造形：翻转 16~96 像素制造与所有已学字区分的新字形
            cand = mutate_matrix(base, rng, flips=(16, 96))
            if is_uniform(cand):
                continue
            if max_sim_to_others(cand, lib, skip_ch=ch) < CONFUSE_THRESH:
                return cand, "variant"
    return None, None


def make_reference(target, lib, rng):
    """
    为目标字生成初始候选（参考）矩阵：
    a. 部件拼接：目标字包含已学字作部件时，用同部件字矩阵左右拼接；
    b. 否则取字符编码距离最近的已学字矩阵做底，较强随机变异。
    返回 (matrix, method) 或 (None, None)
    """
    m, method = gen_concat_candidate(target, lib, rng)
    if m is not None and not is_uniform(m) and max_sim_to_others(m, lib) < CONFUSE_THRESH:
        return m, method
    return gen_variant_candidate(target, lib, rng)


def verify_candidate(cand, target, lib, ref_mat):
    """检验候选矩阵是否被识别为目标字：
    - 与目标字参考矩阵相似度 >= SIM_THRESH（候选确实像目标字字形）；
    - 与库中任何其它字的最大相似度 < CONFUSE_THRESH（不与已有字混淆，保持多样性）。"""
    if is_uniform(cand):
        return False, 0.0
    s_ref = sim(cand, ref_mat)
    if s_ref < SIM_THRESH:
        return False, s_ref
    worst_confuse = max_sim_to_others(cand, lib)
    if worst_confuse >= CONFUSE_THRESH:
        return False, s_ref
    return True, s_ref


def main():
    rng = random.Random(20260829)
    lib = build_library()
    teach = build_teach_table()
    learned_chars = set(lib.keys())
    unlearned = [ch for ch in teach if ch not in learned_chars]
    rng.shuffle(unlearned)
    n0 = len(learned_chars)
    total_learned_new = 0

    # 已持久化字集合（去重：同一次运行同一字只写第一次）
    written_chars = set()
    try:
        for line in open(LEARNED_OUT, encoding="utf-8").read().strip().splitlines():
            r = json.loads(line)
            if r.get("char"):
                written_chars.add(r["char"])
    except FileNotFoundError:
        pass

    for rnd in range(1, MAX_ROUNDS + 1):
        # 每轮选 TARGETS 个目标字（不足则取全部）
        targets = unlearned[:TARGETS]
        if not targets:
            break
        learned_this_round = 0
        remaining = []
        for target in targets:
            ref_mat, method = make_reference(target, lib, rng)
            best_cand, best_s = None, -1.0
            # 变异产生多个候选（含参考本身）
            candidates = [ref_mat] + [mutate_matrix(ref_mat, rng) for _ in range(MAX_CANDS - 1)]
            for cand in candidates:
                ok, s = verify_candidate(cand, target, lib, ref_mat)
                if ok and s > best_s:
                    best_s = s
                    best_cand = cand
            if best_cand is not None:
                lib.setdefault(target, {"matrices": [], "tags": []})
                lib[target]["matrices"].append(best_cand)
                # 从待学表补充 tags
                if teach[target].get("tags"):
                    lib[target]["tags"] = list(
                        dict.fromkeys(lib[target]["tags"] + teach[target]["tags"])
                    )
                learned_this_round += 1
                total_learned_new += 1
                # 持久化：新学会的字写入 learned 文件（同字只保留第一次写入）
                if target not in written_chars:
                    rec = {
                        "schema_version": SCHEMA,
                        "timestamp": time.time(),
                        "char": target,
                        "matrix": best_cand,
                        "tags": teach[target].get("tags", []),
                        "pinyin": teach[target].get("pinyin"),
                        "source": SOURCE,
                    }
                    with open(LEARNED_OUT, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written_chars.add(target)
            else:
                remaining.append(target)
        # 未学会的目标字回到未学会池，供后续轮次再学习
        unlearned = remaining + unlearned[TARGETS:]

        # 多样性约束：单个字最多保留 MAX_MAT_PER_CHAR 个矩阵，超出删相似度最低
        for ch, ent in lib.items():
            mats = ent["matrices"]
            if len(mats) > MAX_MAT_PER_CHAR:
                mats = sorted(mats, key=lambda m: max(sim(m, o) for o in mats if o != m) if len(mats) > 1 else 1.0, reverse=True)
                ent["matrices"] = mats[:MAX_MAT_PER_CHAR]

        print(
            "[STEP212-REV2] round %d learned=%d total_new=%d library_chars=%d"
            % (rnd, learned_this_round, total_learned_new, len(lib))
        )
        if rnd % 10 == 0:
            print(
                "[STEP212-REV2] STAT round=%d learned_this=%d library_total=%d"
                % (rnd, learned_this_round, len(lib))
            )
        if total_learned_new >= LEARN_GOAL:
            break

    with open(LEARNED_OUT, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    print("[STEP212-REV2] written", LEARNED_OUT)
    print("[STEP212-REV2] learned_records =", len(written_chars))
    print("[STEP212-REV2] final_total_learned =", len(lib) - n0)
    print("[STEP212-REV2] final_library_size =", len(lib))
    print("[STEP212-REV2] file_md5 =", file_hash)

    # 哈希链追加（仅一条，针对 hanzi_master_learned.jsonl）
    lines = open(CHAIN, encoding="utf-8").read().strip().splitlines()
    prev_hash = json.loads(lines[-1])["record_hash"]
    ts = time.time()
    record_hash = md5hex(file_hash + prev_hash + str(ts))
    entry = {
        "schema_version": SCHEMA,
        "timestamp": ts,
        "file": LEARNED_OUT,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("[STEP212-REV2] prev_hash =", prev_hash)
    print("[STEP212-REV2] record_hash =", record_hash)


if __name__ == "__main__":
    main()
