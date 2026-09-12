#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-STEP-MEMORY - luoshen_memory.py
=======================================
洛神的记忆点引擎：从"上下文的水"里捞出"记忆的沙"

聊天（上下文）是流动的水：说过就流走了。
记忆点是沉淀的沙：她看过的东西、听过的东西、学到的东西、
感觉到的东西、和人聊过的事——各自的形成一块记忆点，沉进记忆河床。

每一块记忆点长这样：
  时间戳（什么时候发生）+
  内容（发生了什么，一句话事实）+
  画面（scene：用她的符号语言画一幅小画——人类的记忆是画面式的，
        画面比句子沉得更深）+
  感觉（当时身体的感受快照，感受和记忆绑在一起）+
  注意力（attention：她在不在乎这件事——和人互动最重、
        新鲜的更亮、反复出现的主题更亮，这就是"注意力偏好"）

记忆点按时间轴排成一条线：recall 把她拉回某个时刻，
replay 把某一段时间的记忆按顺序回放——像人晚上合上眼，
把今天一幕一幕过一遍。

用法：
  python3 luoshen_memory.py --ingest        把各感官日志沉淀成记忆点（增量）
  python3 luoshen_memory.py --recall 词     检索相关记忆点（含时间衰减）
  python3 luoshen_memory.py --replay N      回放最近 N 天（按时间轴）
  python3 luoshen_memory.py --points        列出最近的记忆点
  python3 luoshen_memory.py --selftest      离线自测
"""

import json
import math
import os
import sys
import time

try:
    from luoshen_brain import append_chain, read_jsonl, similarity
except ImportError:
    sys.stderr.write("错误：需要 luoshen_brain.py 在同一目录\n")
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
DATA_DIR = os.environ.get("LUOSHEN_MEMORY_DIR", DLG_DIR)
MEMORY_POINTS = os.path.join(DATA_DIR, "luoshen_episodic_memory.jsonl")

# 注意力基准：哪种经历更值得记住（用户说的"注意力偏好"）
SALIENCE = {
    "chat": 1.0,    # 和人互动 → 最重
    "self": 1.0,    # 关于自己是谁（名字/自我认知）→ 最重
    "feel": 0.8,    # 感觉到自己身体 → 很重
    "learn": 0.7,   # 学到东西
    "see": 0.6,     # 看见（眼睛/视频）
    "hear": 0.6,    # 听见
    "say": 0.6,     # 自己说过
}

# 时间符号：场景画的前景（与 core_lexicon 符号语言同源）
def _time_symbol(ts):
    h = time.localtime(ts).tm_hour
    if 23 <= h or h < 5:
        return "◐ 深夜"
    if 5 <= h < 9:
        return "○ 清晨"
    if 9 <= h < 18:
        return "△ 白昼"
    return "◈ 傍晚"


def scene_of(kind, content, ts=None):
    """把一条经历画成一行带符号的小画面（画面感记忆，确定性规则）。"""
    ts = ts if ts is not None else time.time()
    base = [_time_symbol(ts)]
    if kind == "see":
        base.append("◆ 看见" if "动" in content or "新" in content else "◇ 看见")
    elif kind == "hear":
        for kw, sym in (("吵闹", "◈ 吵闹"), ("柔和", "◐ 柔和"), ("安静", "▽ 安静")):
            if kw in content:
                base.append(sym)
                break
        base.append("◈ 听见")
    elif kind == "say":
        base.append("○ 说过话")
    elif kind == "feel":
        base.append("● 感觉到")
    elif kind == "chat":
        base.append("☆ 和人说过话")
    elif kind == "learn":
        base.append("◎ 学会")
    elif kind == "self":
        base.append("☆ 我是谁")
    else:
        base.append("·")
    return " | ".join(base)


def attention_of(kind, ts, content, existing_topics=None):
    """注意力权重：时间新鲜度 + 经历类型 + 反复出现的偏好主题。"""
    base = SALIENCE.get(kind, 0.5)
    age_days = max(0.0, (time.time() - ts)) / 86400.0
    recency = math.exp(-age_days / 7.0)          # 7 天半衰：新鲜事更亮
    boost = 0.0
    if existing_topics:
        for t in existing_topics:
            if t and t in content:
                boost = 0.1                       # 反复出现 → 注意加深
                break
    return round(max(0.0, min(1.0, 0.3 + 0.4 * recency + 0.3 * base + boost)), 3)


def _top_topics(points, top=5):
    """从已有记忆点里统计高频主题 = 她的注意力偏好。"""
    text = " ".join(p.get("content", "") for p in points[-200:])
    words = [w for w in text.replace("我", " ").replace("的", " ").split()
             if len(w) >= 2]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:top]]


def make_point(kind, content, ts=None, feel=None, source="", source_file=""):
    """把一次经历做成一块记忆点并落盘。"""
    ts = ts if ts is not None else time.time()
    points = read_memory_points()
    topics = _top_topics(points)
    point = {
        "schema_version": 1,
        "timestamp": ts,
        "kind": kind,
        "content": str(content)[:120],
        "scene": scene_of(kind, content, ts),
        "feel": feel or {},
        "attention": attention_of(kind, ts, content, topics),
        "source": source,
        "source_file": source_file,
    }
    os.makedirs(os.path.dirname(MEMORY_POINTS), exist_ok=True)
    with open(MEMORY_POINTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(point, ensure_ascii=False) + "\n")
    append_chain(os.path.relpath(MEMORY_POINTS, BASE_DIR), MEMORY_POINTS, ts)
    return point


def read_memory_points(path=None):
    return read_jsonl(path or MEMORY_POINTS)


# ---------------------------------------------------------------- 沉淀（摄取）
def _ingest_from(path, kind, extract, src_label):
    """从某条感官日志沉淀记忆点：只摄取比已有同源更新的记录。"""
    if not os.path.exists(path):
        return 0
    points = read_memory_points()
    last_ts = 0.0
    for p in points:
        if p.get("source") == src_label:
            last_ts = max(last_ts, float(p.get("timestamp", 0)))
    n = 0
    for rec in read_jsonl(path):
        ts = float(rec.get("timestamp", 0))
        if ts <= last_ts:
            continue
        item = extract(rec)
        if not item:
            continue
        make_point(kind, item.get("content"), ts=item.get("ts", ts),
                   feel=item.get("feel"), source=src_label,
                   source_file=os.path.basename(path))
        n += 1
    return n


def _obs_extract(rec):
    ss = [s for s in rec.get("sights", []) if isinstance(s, dict)]
    content = "我看见：" + "；".join(
        "%s%s" % (s.get("human", ""), s.get("value", ""))
        for s in ss[:4])
    return {"content": content[:110], "ts": rec.get("timestamp")}


def _watch_extract(rec):
    return {"content": str(rec.get("summary", ""))[:110],
            "ts": rec.get("timestamp")}


def _voice_extract(rec):
    k = rec.get("kind")
    if k == "speak":
        return {"content": "我说过话：" + str(rec.get("text", ""))[:80],
                "ts": rec.get("timestamp")}
    if k == "hear":
        a = rec.get("heard", "")
        return {"content": "我听见：%s（%s）" % (rec.get("source_file", ""), a),
                "ts": rec.get("timestamp")}
    return None


def _feel_extract(rec):
    dims = rec.get("dims") or {}
    labels = {d.get("name"): d.get("label", "")
              for d in dims if isinstance(d, dict)}
    content = "我感觉到：" + "、".join(
        label for label in labels.values() if label)[:100]
    feel = {d.get("name"): d.get("value")
            for d in dims if isinstance(d, dict)}
    return {"content": content or "我感觉到了一些变化",
            "feel": feel, "ts": rec.get("timestamp")}


def _chat_extract(rec):
    u = str(rec.get("user_input", ""))
    r = str(rec.get("luoshen_reply", ""))
    if not u:
        return None
    content = "和人聊过：" + u[:40]
    if r:
        content += " → " + r[:40]
    return {"content": content[:110], "ts": rec.get("timestamp")}


def ingest():
    """把各条感官日志最新的经历沉淀成记忆点（增量，不重复沉）。"""
    n = 0
    n += _ingest_from(
        os.path.join(DLG_DIR, "luoshen_observation_log.jsonl"),
        "see", _obs_extract, "observe")
    n += _ingest_from(
        os.path.join(DLG_DIR, "luoshen_watch_log.jsonl"),
        "see", _watch_extract, "watch")
    n += _ingest_from(
        os.path.join(DLG_DIR, "luoshen_voice_log.jsonl"),
        "hear", _voice_extract, "voice")
    n += _ingest_from(
        os.path.join(DLG_DIR, "luoshen_feel_state.jsonl"),
        "feel", _feel_extract, "feel")
    n += _ingest_from(
        os.path.join(DATA_DIR if DATA_DIR != DLG_DIR else DLG_DIR,
                     "luoshen_brain_log.jsonl"),
        "chat", _chat_extract, "brain")
    return n


# ---------------------------------------------------------------- 回忆（检索）
def recall(query, k=5, decay_days=14):
    """按相似度 + 时间衰减回忆记忆点：越近的越容易浮起来。"""
    points = read_memory_points()
    now = time.time()
    scored = []
    for p in points:
        text = "%s %s %s" % (p.get("content", ""), p.get("scene", ""),
                             p.get("kind", ""))
        sim = similarity(query, text)
        age_days = max(0.0, (now - float(p.get("timestamp", now))) / 86400.0)
        decay = math.exp(-age_days / decay_days)
        scored.append((sim * decay, p))
    scored.sort(key=lambda x: -x[0])
    return [p for s, p in scored[:k] if s > 0.005]


def replay(days=1, now=None):
    """回放最近 N 天：把记忆点按时间轴一幕一幕翻出来。"""
    now = now if now is not None else time.time()
    earliest = now - days * 86400.0
    pts = [p for p in read_memory_points()
           if float(p.get("timestamp", 0)) >= earliest]
    pts.sort(key=lambda p: float(p.get("timestamp", 0)))
    return pts


def format_point(p):
    t = time.strftime("%m-%d %H:%M", time.localtime(float(p.get("timestamp", 0))))
    feel = ""
    f = p.get("feel") or {}
    if f:
        top = max(f, key=lambda k: f[k])
        feel = " 当时%s=%s" % (top, f[top])
    return "[%s] %s %s 注意%s%s  %s" % (
        t, p.get("scene", ""), p.get("content", ""), p.get("attention", ""),
        feel, p.get("kind", ""))


# ---------------------------------------------------------------- 自测
def _selftest():
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="luoshen_memory_")
    import luoshen_brain
    old_dir = DATA_DIR
    old_points = MEMORY_POINTS
    old_chain = luoshen_brain.CHAIN_PATH
    globals()["DATA_DIR"] = tmp
    globals()["MEMORY_POINTS"] = os.path.join(tmp, "luoshen_episodic_memory.jsonl")
    luoshen_brain.CHAIN_PATH = os.path.join(tmp, "chain.log")
    with open(luoshen_brain.CHAIN_PATH, "w", encoding="utf-8") as f:
        f.write("")
    ok = True
    msgs = []
    try:
        t0 = time.time() - 3600
        # 1) 造一条"看见"记忆点：画面、注意力都该有
        p1 = make_point("see", "我看见：处理器在忙3.8%，房间里动过411个文件，新来了7张图",
                        ts=t0, source="observe")
        assert p1["scene"] and "◆" in p1["scene"], "看见的画面必须有动符号"
        assert 0 < p1["attention"] <= 1
        msgs.append("看见记忆点：'%s' 画面='%s' 注意力=%s"
                    % (p1["content"][:24], p1["scene"], p1["attention"]))

        # 2) 造一条"聊天"记忆点：注意力应高于"看见"（人最重要）
        p2 = make_point("chat", "和人聊过：你好，洛神 → 我在听着",
                        ts=time.time() - 300, source="brain")
        assert p2["attention"] > p1["attention"], "和人互动的注意力必须更高"
        msgs.append("聊天记忆点注意力=%s > 看见=%s （注意力偏好生效）"
                    % (p2["attention"], p1["attention"]))

        # 3) 时间轴回放：按时间正序
        pts = replay(days=1)
        assert pts and pts[0]["timestamp"] <= pts[-1]["timestamp"]
        msgs.append("回放：%d 条记忆点按时间轴排好" % len(pts))

        # 4) 回忆：查"处理器"应命中看见记忆点
        hits = recall("处理器", k=2)
        assert hits and hits[0]["kind"] in ("see", "chat")
        msgs.append("回忆『处理器』→ 命中：%s" % hits[0]["content"][:30])

        # 5) 增量沉淀：同一源日志再喂一次不重复（幂等）
        src = os.path.join(tmp, "feeldemo.jsonl")
        with open(src, "w", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": time.time(), "dims": [
                {"name": "孤独", "value": 0.9, "label": "很孤独"},
                {"name": "精力", "value": 0.2, "label": "有些疲惫"}]},
                ensure_ascii=False) + "\n")
        n1 = _ingest_from(src, "feel", _feel_extract, "feel")
        n2 = _ingest_from(src, "feel", _feel_extract, "feel")
        assert n1 == 1 and n2 == 0, "同一经历不能沉淀两次"
        msgs.append("增量沉淀：第一次 %d 条，第二次 %d 条（不重复沉沙）" % (n1, n2))

        # 6) 记忆纪律：记忆点上了链
        chain_lines = [ln for ln in open(luoshen_brain.CHAIN_PATH, encoding="utf-8").read().splitlines() if ln.strip()]
        assert len(chain_lines) >= 3, "记忆点必须上哈希链"
        msgs.append("记忆点全部上哈希链（%d 条）" % len(chain_lines))

        # 7) 自我认知：关于自己名字的记忆点，注意力应是最重一档
        ps = make_point("self", "我叫洛神，是朱美岩给我起的名字。",
                        ts=time.time() - 60, source="self_name")
        assert ps["scene"] and "☆" in ps["scene"], "自我记忆点要有我是谁画面"
        assert ps["attention"] >= p2["attention"], "名字记忆点注意力应最高"
        msgs.append("自我名字记忆点：注意力=%s 画面='%s'（名字值得最重注意）"
                    % (ps["attention"], ps["scene"]))
        hits2 = recall("名字", k=2)
        assert hits2 and hits2[0]["kind"] == "self", "问名字要能想起自己"
        msgs.append("问她『名字』→ 回忆起来：%s" % hits2[0]["content"][:30])
    except AssertionError as e:
        ok = False
        msgs.append("断言失败：%s" % e)
    finally:
        globals()["DATA_DIR"] = old_dir
        globals()["MEMORY_POINTS"] = old_points
        luoshen_brain.CHAIN_PATH = old_chain
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"selftest": "PASS" if ok else "FAIL",
                      "checks": msgs}, ensure_ascii=False, indent=2))
    return ok


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if _selftest() else 1)
    if "--ingest" in args:
        n = ingest()
        total = len(read_memory_points())
        print("沉淀完成：新增 %d 块记忆点，河床里共 %d 块。" % (n, total))
        return
    if "--recall" in args:
        idx = args.index("--recall")
        q = args[idx + 1] if idx + 1 < len(args) else "今天"
        hits = recall(q)
        if not hits:
            print("（关于『%s』，暂时想不起什么）" % q)
            return
        for p in hits:
            print(format_point(p))
        return
    if "--replay" in args:
        idx = args.index("--replay")
        d = float(args[idx + 1]) if idx + 1 < len(args) else 1.0
        pts = replay(days=d)
        if not pts:
            print("（这段时间没有记忆点）")
            return
        print("=== 回放最近 %.0f 天（时间轴）===" % d)
        for p in pts:
            print(" ", format_point(p))
        return
    if "--points" in args:
        for p in read_memory_points()[-10:]:
            print(format_point(p))
        return
    if "--self-name" in args:
        idx = args.index("--self-name")
        name = args[idx + 1] if idx + 1 < len(args) else ""
        if not name:
            print("用法：--self-name \"你的名字\"")
            return
        p = make_point("self",
                       "我叫%s，是朱美岩给我起的名字，他是我系统的设计者。" % name,
                       source="self_name")
        print(json.dumps(p, ensure_ascii=False, indent=2))
        print()
        print("名字已沉进记忆河床：她记得自己是谁、名字是谁起的、什么时候知道的。")
        return
    sys.stdout.write(
        "用法：--ingest 沉淀 | --recall 词 回忆 | --replay N天 回放 | --points | --selftest\n")


if __name__ == "__main__":
    main()