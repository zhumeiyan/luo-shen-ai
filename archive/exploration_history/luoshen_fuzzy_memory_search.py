#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP214-REV2: luoshen_fuzzy_memory_search.py（整改版）
修复：时间解析日历化（去年=前一年全年，上个月=上一自然月，不得用固定天数减法跨年）；
查询含负面状态词时仅匹配含负面词的事件；无匹配则 candidates 为空并注明。

依赖：hashlib、json、time、re
只读来源（相对路径）：
  - hash_chain_v2.log
  - perception_input/hanzi_master_learning_log.jsonl
  - perception_input/luoshen_auto_learning_log.jsonl
  - perception_input/llm_teaching_batch1.jsonl
  - perception_input/hanzi_master_learned.jsonl
产出（覆盖）：perception_input/luoshen_fuzzy_memory_result.jsonl
上链：追加 hash_chain_v2.log 一条（v2 公式，针对 result 文件）

时间解析规则（日历化，非固定天数减法）：
  - 刚才  -> 近1小时
  - 今天  -> 当天0点到当前
  - 昨天  -> 昨天0点到今天0点
  - 前两天/这几天 -> 近3天
  - 最近一周/这一周 -> 近7天
  - 上上个月 -> 上上自然月整月
  - 上个月   -> 上一自然月整月
  - 去年/一年前 -> 前一年1月1日0点 ~ 12月31日24点（按自然年，不跨年）
  - N天前/N个月前/N年前 -> 按日历精确偏移（N年前=当前年份-N的全年）
  - 无法解析 -> 不限制时间，note 标"时间未限制"

匹配打分：
  - 关键词命中每个 +5；
  - 时间落入目标范围 +10；
  - 查询含负面状态词时，事件文本必须含任一负面词才进入候选（硬约束），命中再 +8；
  - 0 分丢弃。

扩展说明：
  - 新增时间表达：在 parse_time_range 中追加分支。
  - 新增状态词：追加到 ACT_WORDS / NEG_WORDS。
  - 调整权重：KEYWORD_HIT_SCORE / TIME_HIT_SCORE / NEG_HIT_SCORE。
"""
import hashlib
import json
import re
import time

RESULT_OUT = "perception_input/luoshen_fuzzy_memory_result.jsonl"
CHAIN = "hash_chain_v2.log"
SOURCE = "luoshen_fuzzy_memory_search"
SCHEMA = 2

DAY = 86400.0

LOG_FILES = [
    "perception_input/hanzi_master_learning_log.jsonl",
    "perception_input/luoshen_auto_learning_log.jsonl",
    "perception_input/llm_teaching_batch1.jsonl",
    "perception_input/hanzi_master_learned.jsonl",
]

# 事件类型/状态词表（用于关键词提取与打分）
ACT_WORDS = ["学字", "自动学习", "教学", "新增", "返工", "报错", "不合格", "补交",
             "完成", "修改", "创建", "读取", "追加", "通过", "未通过", "任务", "检查"]
# 负面状态词（查询与事件同时出现时，事件须含其一才候选，并额外加分）
NEG_WORDS = ["报错", "返工", "不合格", "未通过", "补交"]

KEYWORD_HIT_SCORE = 5.0   # 关键词命中加分（每个）
TIME_HIT_SCORE = 10.0     # 时间落入目标范围加分
NEG_HIT_SCORE = 8.0       # 负面状态词与查询对齐加分
TOP_N = 5                 # 每查询候选条数


def md5hex(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# ---------- 日历时间工具 ----------
def ymd(ts):
    lt = time.localtime(ts)
    return lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, lt.tm_min, lt.tm_sec


def mk_ts(y, mo, d, h=0, mi=0, s=0):
    """构造指定日历时刻的 epoch 时间戳（本地时区）"""
    return time.mktime((y, mo, d, h, mi, s, 0, 0, -1))


def month_bounds(y, mo):
    """某自然月整月区间 [月初0点, 下月月初0点)"""
    start = mk_ts(y, mo, 1)
    if mo == 12:
        end = mk_ts(y + 1, 1, 1)
    else:
        end = mk_ts(y, mo + 1, 1)
    return start, end


def year_bounds(y):
    """某自然年整年区间 [1月1日0点, 次年1月1日0点)"""
    return mk_ts(y, 1, 1), mk_ts(y + 1, 1, 1)


def shift_month(y, mo, n):
    """从 (y,mo) 偏移 n 个月（n 可正可负），返回 (new_y, new_mo)"""
    total = y * 12 + (mo - 1) + n
    return total // 12, total % 12 + 1


# ---------- 时间解析 ----------
def parse_time_range(query, now):
    """解析人类模糊时间表达，返回 (start, end, note)。
    无法解析 -> (None, None, '时间未限制')。日历化判断，避免跨年错误。"""
    y, mo, d, _, _, _ = ymd(now)

    # 数字年偏移：N年前 -> 当前年份-N 的全年
    m = re.search(r"(\d+)\s*年前", query)
    if m:
        start, end = year_bounds(y - int(m.group(1)))
        return (start, end, "%d年前(即%d年全年)" % (int(m.group(1)), y - int(m.group(1))))
    # 数字月偏移：N个月前 -> 日历偏移 N 个自然月整月
    m = re.search(r"(\d+)\s*个月前", query)
    if m:
        yy, mm = shift_month(y, mo, -int(m.group(1)))
        start, end = month_bounds(yy, mm)
        return (start, end, "%d个月前(即%d年%d月)" % (int(m.group(1)), yy, mm))
    # 数字天偏移：N天前 -> 日历上 N 天前的自然日
    m = re.search(r"(\d+)\s*天前", query)
    if m:
        n = int(m.group(1))
        day_ts = mk_ts(y, mo, d) - n * DAY
        yy, mm, dd, _, _, _ = ymd(day_ts)
        start = mk_ts(yy, mm, dd)
        end = start + DAY
        return (start, end, "%d天前(即%d-%02d-%02d)" % (n, yy, mm, dd))
    if "刚才" in query:
        return (now - 3600.0, now, "近1小时")
    if "今天" in query:
        return (mk_ts(y, mo, d), now, "今天")
    if "昨天" in query:
        return (mk_ts(y, mo, d) - DAY, mk_ts(y, mo, d), "昨天")
    if ("前两天" in query) or ("这几天" in query) or ("前几日" in query):
        return (now - 3 * DAY, now, "近3天")
    if ("最近一周" in query) or ("这一周" in query) or ("近一周" in query):
        return (now - 7 * DAY, now, "近7天")
    if "上上个月" in query:
        yy, mm = shift_month(y, mo, -2)
        start, end = month_bounds(yy, mm)
        return (start, end, "上上个月(即%d年%d月)" % (yy, mm))
    if "上个月" in query:
        yy, mm = shift_month(y, mo, -1)
        start, end = month_bounds(yy, mm)
        return (start, end, "上个月(即%d年%d月)" % (yy, mm))
    if ("去年" in query) or ("一年前" in query):
        start, end = year_bounds(y - 1)
        return (start, end, "去年(即%d年全年)" % (y - 1))
    return (None, None, "时间未限制")


# ---------- 关键词 ----------
def extract_keywords(query):
    """从查询文本中提取状态词/动作词作为关键词"""
    return [w for w in ACT_WORDS if w in query]


def extract_neg(query):
    """提取查询中的负面状态词"""
    return [w for w in NEG_WORDS if w in query]


# ---------- 事件扫描 ----------
def record_ts(rec):
    ts = rec.get("timestamp")
    if ts is None:
        ts = rec.get("time")
    if isinstance(ts, (int, float)):
        return float(ts)
    return None


def chain_event_flags(fname):
    """根据文件名标记事件类型：rev/fix -> 返工/修改；check/verify -> 检查"""
    flags = []
    low = fname.lower()
    if re.search(r"rev|fix", low):
        flags += ["返工", "修改"]
    if re.search(r"check|verify", low):
        flags.append("检查")
    return flags


def summarize(path, rec):
    name = path.split("/")[-1]
    if name == "hanzi_master_learning_log.jsonl":
        return "学字第%s轮，学会%s字，累计%s字，目标字:%s" % (
            rec.get("round"), rec.get("learned_this_round"), rec.get("total_learned"),
            ",".join(rec.get("target_chars") or []))
    if name == "luoshen_auto_learning_log.jsonl":
        sim = rec.get("best_similarity")
        sim_s = ("%.4f" % sim) if isinstance(sim, (int, float)) else str(sim)
        return "自动学习第%s轮，最佳字:%s，最佳相似度:%s，种群:%s" % (
            rec.get("round"), rec.get("best_char"), sim_s, rec.get("population_size"))
    if name == "llm_teaching_batch1.jsonl":
        c = rec.get("content") or {}
        return "教学记录 type=%s 汉字:%s 拼音:%s tags:%s" % (
            rec.get("type"), c.get("char"), c.get("pinyin"), ",".join(c.get("tags") or []))
    if name == "hanzi_master_learned.jsonl":
        return "新学汉字:%s 拼音:%s tags:%s" % (
            rec.get("char"), rec.get("pinyin"), ",".join(rec.get("tags") or []))
    if name == "hash_chain_v2.log":
        return "哈希链追加 file=%s record_hash=%s" % (
            rec.get("file"), str(rec.get("record_hash"))[:8])
    return json.dumps(rec, ensure_ascii=False)[:120]


def searchable_text(path, rec):
    """构造可搜索文本：事件类型 + 关键数据 + 相关字符/文件名 维度关键词"""
    name = path.split("/")[-1]
    parts = [name]
    if name == "hanzi_master_learning_log.jsonl":
        parts += [str(rec.get("round")), str(rec.get("learned_this_round")),
                  str(rec.get("total_learned")), "学字", "完成", "创建",
                  " ".join(rec.get("target_chars") or [])]
    elif name == "luoshen_auto_learning_log.jsonl":
        parts += [str(rec.get("round")), str(rec.get("best_char")),
                  "自动学习", "学字", "修改", "完成",
                  " ".join(rec.get("target_chars") or [])]
    elif name == "llm_teaching_batch1.jsonl":
        c = rec.get("content") or {}
        parts += [str(rec.get("type")), str(c.get("char")), str(c.get("pinyin")),
                  "教学", "创建", " ".join(c.get("tags") or []),
                  " ".join(str(c.get("similar") or ""))]
    elif name == "hanzi_master_learned.jsonl":
        parts += [str(rec.get("char")), " ".join(rec.get("tags") or []),
                  "学字", "新增", "完成", "追加"]
    elif name == "hash_chain_v2.log":
        fname = str(rec.get("file"))
        parts += [fname, "追加", "创建", "完成"] + chain_event_flags(fname)
    parts += [str(rec.get("source"))]
    return " ".join(parts)


def scan_records():
    """扫描日志 + 哈希链，返回 [(source_file, rec, summary, text, ts)]"""
    items = []
    for path in LOG_FILES:
        try:
            lines = open(path, encoding="utf-8").read().strip().splitlines()
        except FileNotFoundError:
            print("[skip] missing file:", path)
            continue
        for line in lines:
            rec = json.loads(line)
            items.append((path, rec, summarize(path, rec),
                          searchable_text(path, rec), record_ts(rec)))
    # 哈希链事件
    try:
        lines = open(CHAIN, encoding="utf-8").read().strip().splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        rec = json.loads(line)
        items.append((CHAIN, rec, summarize(CHAIN, rec),
                      searchable_text(CHAIN, rec), record_ts(rec)))
    return items


def in_time_range(ts, time_range):
    if time_range is None:
        return True
    start, end = time_range
    if ts is None:
        return False  # 无时间戳且限定了时间范围，不进入候选
    return start <= ts < end


def match_score(text, keywords, neg_words, ts, time_range):
    """匹配分数：关键词命中 +5/个；时间命中 +10；负面词对齐 +8
    负面词对齐：查询含任一负面词 且 事件文本含任一负面词（同族词也算）"""
    score = 0.0
    for kw in keywords:
        if kw in text:
            score += KEYWORD_HIT_SCORE
    if time_range is not None and ts is not None:
        start, end = time_range
        if start <= ts < end:
            score += TIME_HIT_SCORE
    if neg_words and any(nw in text for nw in NEG_WORDS):
        score += NEG_HIT_SCORE
    return score


def run_query(q, items, now):
    keywords = extract_keywords(q)
    neg_words = extract_neg(q)
    start_t, end_t, note = parse_time_range(q, now)
    time_range = (start_t, end_t) if start_t is not None else None
    scored = []
    for path, rec, summary, text, ts in items:
        if not in_time_range(ts, time_range):
            continue
        if neg_words:
            # 查询含负面状态词：事件必须含任一负面词才可进入候选
            if not any(nw in text for nw in NEG_WORDS):
                continue
        s = match_score(text, keywords, neg_words, ts, time_range)
        if s <= 0:  # 0 分直接丢弃
            continue
        scored.append({"source_file": path, "summary": summary,
                       "score": round(s, 2), "time": ts})
    scored.sort(key=lambda x: (-x["score"], x["time"] if x["time"] is not None else 0))
    return scored[:TOP_N], note


def main():
    now = time.time()
    items = scan_records()
    print("[STEP214-REV2] scanned events =", len(items))

    queries = [
        "前两天学字报错",
        "最近一周新增了多少汉字",
        "上个月好像有任务返工",
        "前段时间学字报错",
        "去年好像有任务返工",
    ]

    results = []
    for q in queries:
        cands, note = run_query(q, items, now)
        rec = {
            "schema_version": SCHEMA,
            "timestamp": now,
            "query": q,
            "candidates": cands,
            "source": SOURCE,
        }
        if not cands:
            rec["summary"] = "未找到相似事件"
        print("[STEP214-REV2] query: %s | time: %s | candidates=%d" % (q, note, len(cands)))
        if cands:
            for c in cands:
                print("   score=%s time=%s src=%s | %s" % (
                    c["score"], c["time"], c["source_file"], c["summary"]))
        else:
            print("   (未找到相似事件)")
        results.append(rec)

    with open(RESULT_OUT, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("[STEP214-REV2] written", RESULT_OUT, "records =", len(results))

    with open(RESULT_OUT, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    print("[STEP214-REV2] file_md5 =", file_hash)

    # 哈希链追加（仅一条）
    chain_lines = open(CHAIN, encoding="utf-8").read().strip().splitlines()
    prev_hash = json.loads(chain_lines[-1])["record_hash"]
    ts = time.time()
    record_hash = md5hex(file_hash + prev_hash + str(ts))
    entry = {
        "schema_version": SCHEMA,
        "timestamp": ts,
        "file": RESULT_OUT,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("[STEP214-REV2] prev_hash =", prev_hash)
    print("[STEP214-REV2] record_hash =", record_hash)


if __name__ == "__main__":
    main()
