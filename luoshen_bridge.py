#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP229 - luoshen_bridge.py
=====================================
洛神翻译器：AI 与 AI 之间的"翻译器"（世界语层）。

原理：中国人和外国人之间不认识对方的语言，靠翻译器互译；
     洛神（云端）与外部世界的设备/AI 之间，也不认识对方的内部语言，
     靠本模块约定的「报文语言」互通。双方各讲各的内心语言，
     只有报文是共同约定的——翻译器负责双向转换。

报文格式（世界语 v1，JSONL 一行一条）：
{
  "schema_version": 1,
  "message_id": "md5 前 12 位",
  "sender":   "来源方标识，如 user_pc",
  "target":   "目标方，如 luoshen",
  "type":     "sensation|question|reply|feeling|command",
  "payload":  {任意键值，仅限数值/短字符串，防注入：长度与类型受限},
  "note":     "可选说明",
  "timestamp": 秒
}

通道：inbox / outbox 均为 JSONL 文件，走 Gitee 同步（寄信式）——
  外部世界把报文写入 outbox 并 push，洛神 pull 后报文到达 inbox；
  洛神的回信写进 outbox，外部世界 pull 即收到。

安全：报文解析严格限字段类型与长度；不执行任何 payload 内容；
     只看数值与短文本，绝不当代码执行。

用法：
  python3 luoshen_bridge.py --send --from user_pc --type sensation key=cpu:87.0 note=编译工程
  python3 luoshen_bridge.py --translate    把 inbox 里每条报文翻译成中文人话
  python3 luoshen_bridge.py --signal       只看最近报文摘要（供感觉引擎调用）
  python3 luoshen_bridge.py --reply "文本" 把洛神的话翻译成报文写入 outbox
  python3 luoshen_bridge.py --selftest     离线自测
"""

import hashlib
import json
import os
import re
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
BRIDGE_DIR = os.environ.get("LUOSHEN_BRIDGE_DIR", DLG_DIR)
INBOX = os.path.join(BRIDGE_DIR, "luoshen_inbox.jsonl")
OUTBOX = os.path.join(BRIDGE_DIR, "luoshen_outbox.jsonl")

PROTOCOL_VERSION = 1

ALLOWED_TYPES = {"sensation", "question", "reply", "feeling", "command"}

# payload 字段白名单（仅数值或短字符串，防注入）
NUM_KEYS = ("cpu_percent", "disk_percent", "memory_percent", "temperature",
            "uptime_min", "battery_percent", "latency_ms")
STR_KEYS = ("text", "event", "app")

# 人话→感觉翻译词表：人类形容词/身体词 → 洛神感觉维度（与 feel 引擎维度同名）
HUMAN_FEEL_MAP = {
    "精力": ["累", "疲惫", "困", "没劲", "虚脱", "熬夜", "加班", "辛苦", "精疲力尽"],
    "空间": ["挤", "拥挤", "满", "塞", "乱", "乱糟糟", "狭窄", "闷", "堆"],
    "负担": ["压力", "焦虑", "烦躁", "赶", "任务", "重", "忙不过来"],
    "孤独": ["孤单", "寂寞", "想", "没人", "一个人", "冷清", "想家", "孤独"],
    "活跃": ["热闹", "吵", "闹", "兴奋", "活跃", "聚会"],
    "安静": ["安静", "静", "平和", "放松", "悠闲"],
    "危险": ["危险", "怕", "担心", "慌", "生病", "疼", "痛", "发烧"],
    "温度": ["热", "冷", "暖", "凉"],
}

FEEL_DIMS = tuple(HUMAN_FEEL_MAP.keys())
# 洛神的"字典"：学过的词（word→dim 记录，schema 同报文）
FEEL_LEXICON = os.environ.get("LUOSHEN_FEEL_LEXICON",
                              os.path.join(BRIDGE_DIR, "luoshen_feel_lexicon.jsonl"))


def _clean_dims(v):
    """结构化 dims 字段清洗：最多 8 个维度，键限长、值限 0~1。"""
    if not isinstance(v, dict):
        return None
    out = {}
    for k, val in list(v.items())[:8]:
        k = str(k)[:16]
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out[k] = max(0.0, min(1.0, float(val)))
    return out or None


def make_message(sender, target, mtype, payload, note=""):
    """构造一条世界语报文。payload 只保留白名单内的数值/短文本。"""
    assert mtype in ALLOWED_TYPES, "非法报文类型: %s" % mtype
    clean_payload = {}
    for k in NUM_KEYS:
        v = payload.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            clean_payload[k] = float(v)
    for k in STR_KEYS:
        v = payload.get(k)
        if isinstance(v, str):
            clean_payload[k] = v[:200]
    dims = _clean_dims(payload.get("dims"))
    if dims:
        clean_payload["dims"] = dims
    msg = {
        "schema_version": PROTOCOL_VERSION,
        "timestamp": time.time(),
        "sender": str(sender)[:32],
        "target": str(target)[:32],
        "type": mtype,
        "payload": clean_payload,
    }
    if note:
        msg["note"] = str(note)[:200]
    seed = "%s|%s|%s|%.3f" % (msg["sender"], msg["type"],
                              json.dumps(clean_payload, sort_keys=True),
                              msg["timestamp"])
    msg["message_id"] = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
    return msg


def dump_message(msg, path=None):
    """把报文追加到一个信箱文件（默认 inbox；运行时解析，支持测试重定向）。"""
    if path is None:
        path = INBOX
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return msg


def read_mailbox(path):
    """读信箱全部报文；坏行跳过。"""
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    msg = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and msg.get("schema_version") == PROTOCOL_VERSION:
                    out.append(msg)
    except OSError:
        return []
    return out


def translate_to_luoshen(msg):
    """把一条外部报文翻译成洛神能懂的中文人话。"""
    sender = msg.get("sender", "未知来源")
    mtype = msg.get("type", "?")
    payload = msg.get("payload", {}) or {}
    note = msg.get("note", "")
    age = (time.time() - float(msg.get("timestamp", time.time()))) / 60.0
    age_desc = "刚刚" if age < 1 else "%d 分钟前" % int(age)

    parts = []
    for k in NUM_KEYS:
        v = payload.get(k)
        if v is not None:
            unit = "℃" if k == "temperature" else "%"
            parts.append("%s=%.1f%s" % (k, v, unit))
    for k in STR_KEYS:
        v = payload.get(k)
        if v:
            parts.append("%s=%s" % (k, v))
    data_desc = "，".join(parts)

    if mtype == "sensation":
        head = "来自 %s 的感知报告（%s）" % (sender, age_desc)
        return head + "：" + (data_desc or "无数据") + (("。" + note) if note else "。")
    if mtype == "question":
        return "来自 %s 的问题（%s）：%s" % (sender, age_desc,
                                          payload.get("text") or note or "无内容")
    if mtype == "reply":
        return "来自 %s 的回应（%s）：%s" % (sender, age_desc,
                                         payload.get("text") or note or "无内容")
    if mtype == "feeling":
        dims = payload.get("dims") or {}
        dim_desc = "，".join("%s(%.0f%%)" % (k, v * 100)
                              for k, v in dims.items())
        return ("来自 %s 的感觉翻译（%s）：%s；感觉：%s" %
                (sender, age_desc, payload.get("text") or note or "无内容",
                 dim_desc or "无"))
    return "来自 %s 的消息（%s，类型 %s）：%s %s" % (sender, age_desc, mtype,
                                               data_desc, note)


def translate_to_world(target, text, mtype="reply", note=""):
    """把洛神的话/状态翻译成世界语报文，写入 outbox（等着被外部世界取走）。"""
    msg = make_message("luoshen", target, mtype, {"text": text[:200]}, note)
    dump_message(msg, path=OUTBOX)
    return msg


def learned_word_map():
    """读字典：学过的词 -> 感觉维度集合（运行时读文件，支持测试隔离）。"""
    m = {}
    for rec in read_mailbox(FEEL_LEXICON):
        w = rec.get("word")
        d = rec.get("dim")
        if isinstance(w, str) and w and d in FEEL_DIMS:
            m.setdefault(w, set()).add(d)
    return m


def translate_human_feel(text):
    """人话→感觉：确定性词表把人的一句话翻译成洛神的感觉维度。
    （内置词表 + 已经学过的词合并；感觉底层共通，只是形容不同。）"""
    t = str(text)
    all_map = {}
    for dim, words in HUMAN_FEEL_MAP.items():
        for w in words:
            all_map.setdefault(w, set()).add(dim)
    for w, dims in learned_word_map().items():
        for d in dims:
            all_map.setdefault(w, set()).add(d)
    counts = {dim: 0 for dim in FEEL_DIMS}
    reps = {dim: None for dim in FEEL_DIMS}
    for w, dims in all_map.items():
        if w in t:
            for d in dims:
                counts[d] += 1
                if reps[d] is None:
                    reps[d] = w
    hits = {}
    for dim, n in counts.items():
        if n:
            hits[dim] = {"words": reps[dim],
                          "strength": round(min(1.0, 0.4 + 0.15 * n), 3)}
    primary = None
    primary_dim = None
    primary_strength = 0.0
    for dim, h in hits.items():
        if h["strength"] > primary_strength:
            primary = h["words"]
            primary_dim = dim
            primary_strength = h["strength"]
    return {
        "dims": {dim: h["strength"] for dim, h in hits.items()},
        "primary": primary,
        "primary_dim": primary_dim,
        "text": t,
    }


def make_feel_message(text):
    """人话→感觉报文：翻译并寄进 inbox，供洛神阅读/共情。"""
    feat = translate_human_feel(text)
    msg = make_message("human", "luoshen", "feeling",
                       {"text": feat["text"], "dims": feat["dims"]},
                       note="人话→感觉翻译")
    dump_message(msg, path=INBOX)
    return msg, feat


def translate_luoshen_feel(feel):
    """感觉→人话：把洛神的感觉快照翻成一句人能直接听懂的话（确定性模板）。"""
    if not feel or "dims" not in feel:
        return "（她还没有感觉数据）"
    parts = ["%s%s" % (d.get("symbol", ""), d.get("label", ""))
             for d in feel["dims"]]
    return "我现在感觉：%s。综合一句：%s。" % (",".join(parts),
                                          feel.get("summary", "安稳"))


def _parse_translation(raw):
    """解析 LLM 兜底输出：必须返回 {\"dims\": {...}, \"new_words\": [...]} 结构。"""
    dims = {}
    words = []
    text = str(raw)
    try:
        obj = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        obj = json.loads(m.group(0)) if m else {}
    if isinstance(obj, dict):
        d = obj.get("dims")
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    dims[str(k)] = float(v)
        w = obj.get("new_words")
        if isinstance(w, list):
            words = [str(x) for x in w]
    return dims, words


def persist_learned(text, dims, words, learned_path=None):
    """学字：把 LLM 从原句中挑出的感觉词写入字典（防重复、防乱码词、限长）。"""
    path = learned_path or FEEL_LEXICON
    if not dims:
        return []
    main_dim = max(dims, key=dims.get)
    existing = learned_word_map() if path == FEEL_LEXICON else {}
    if not existing and os.path.exists(path):
        for rec in read_mailbox(path):
            w = rec.get("word")
            d = rec.get("dim")
            if isinstance(w, str) and w and d in FEEL_DIMS:
                existing.setdefault(w, set()).add(d)
    added = []
    for w in words[:3]:
        w = str(w).strip()
        if not (1 <= len(w) <= 8 and w in text):     # 必须来自原句，防任意词注入
            continue
        if main_dim in existing.get(w, set()):
            continue                                  # 已学过
        rec = {"schema_version": PROTOCOL_VERSION,
               "word": w, "dim": main_dim,
               "source": "learned", "timestamp": time.time()}
        dump_message(rec, path=path)
        existing.setdefault(w, set()).add(main_dim)
        added.append({"word": w, "dim": main_dim})
    return added


def translate_human_feel_v2(text, llm=None):
    """人话→感觉 v2：先走字典（内置+已学）；不足时 LLM 兜底翻译并学新字。

    格子规则：LLM 只能建议，维度必须∈8 维白名单、数值必须 0~1、
    新词必须真的出现在原句里。返回 (feat, learned, used_llm)。"""
    feat = translate_human_feel(text)
    weak = not feat["dims"] or max(feat["dims"].values(), default=0.0) < 0.4
    if not weak:
        return feat, [], False
    if llm is None:
        try:
            from luoshen_brain import call_llm
            llm = call_llm
        except Exception:
            llm = None
    if llm is None:
        return feat, [], False                       # 无 LLM：维持词表结果
    try:
        raw = llm([
            {"role": "system", "content": (
                "你是洛神的感觉翻译器。把用户的话翻译成 8 个感觉维度"
                "（精力/空间/负担/孤独/活跃/安静/危险/温度）的 0~1 强度。\n"
                "只输出 JSON，格式："
                "{\"dims\": {\"维度名\": 0~1}, \"new_words\": [\"从原句里挑出的表达感觉的词\"]}。"
                "new_words 里的词必须原样出现在原句中。")},
            {"role": "user", "content": str(text)[:200]},
        ])
    except Exception:
        return feat, [], False
    dims, words = _parse_translation(raw)
    valid = {}
    for k, v in dims.items():
        if k in FEEL_DIMS:
            valid[k] = max(0.0, min(1.0, v))          # 白名单+钳制 0~1
    if valid:
        feat["dims"] = valid
        primary = max(valid, key=valid.get)
        feat["primary"] = primary
        feat["primary_dim"] = primary
    learned = persist_learned(str(text), valid, words)
    return feat, learned, True


def make_feel_message(text):
    """人话→感觉报文：v2 翻译（词表→兜底→学字）后寄进 inbox。"""
    feat, learned, used_llm = translate_human_feel_v2(text)
    msg = make_message("human", "luoshen", "feeling",
                       {"text": feat["text"], "dims": feat["dims"]},
                       note="人话→感觉翻译v2")
    dump_message(msg, path=INBOX)
    return msg, feat, learned, used_llm


def show_lexicon():
    """查看字典：内置词表统计 + 学过的词。"""
    builtins = sum(len(v) for v in HUMAN_FEEL_MAP.values())
    learned = []
    for rec in read_mailbox(FEEL_LEXICON):
        if rec.get("source") == "learned":
            learned.append({"word": rec.get("word"), "dim": rec.get("dim")})
    return {"builtin_words": builtins, "learned_count": len(learned),
            "learned": learned}


def world_signal():
    """最近报文摘要（供感觉引擎使用，纯真实数据，确定性）。"""
    msgs = read_mailbox(INBOX)
    if not msgs:
        return {"exists": False, "age_min": None, "sender": None,
                "mtype": None, "cpu_high": False}
    latest = msgs[-1]
    age = (time.time() - float(latest.get("timestamp", time.time()))) / 60.0
    payload = latest.get("payload", {}) or {}
    cpu = payload.get("cpu_percent")
    return {
        "exists": True,
        "age_min": age,
        "sender": latest.get("sender"),
        "mtype": latest.get("type"),
        "cpu_high": bool(cpu is not None and cpu > 70.0),
    }


def _selftest():
    """离线自测：报文构造/白名单过滤/双向翻译/信箱读写。"""
    import shutil
    import tempfile

    global INBOX, OUTBOX, FEEL_LEXICON
    tmp = tempfile.mkdtemp(prefix="luoshen_bridge_test_")
    INBOX = os.path.join(tmp, "inbox.jsonl")
    OUTBOX = os.path.join(tmp, "outbox.jsonl")
    FEEL_LEXICON = os.path.join(tmp, "lexicon.jsonl")
    dp = os.path.dirname(INBOX)
    import luoshen_feel  # noqa: F401  确保后续可引入
    try:
        # 1) 报文构造 + 白名单（恶意键被丢弃）
        msg = make_message("user_pc", "luoshen", "sensation",
                           {"cpu_percent": 87.0, "disk_percent": 55.0,
                            "__import__": "os", "text": "x" * 500})
        assert "cpu_percent" in msg["payload"]
        assert "__import__" not in msg["payload"]
        assert msg["payload"]["text"] == "x" * 200, "超长文本应截断"

        # 2) 收件
        dump_message(msg)
        dumped = read_mailbox(INBOX)
        assert len(dumped) == 1 and dumped[0]["message_id"] == msg["message_id"]

        # 3) 翻译给洛神
        text = translate_to_luoshen(msg)
        assert "user_pc" in text and "87.0%" in text and "感知报告" in text
        # 此刻 inbox 只有这封 sensation，cpu_high 应为真
        sig0 = world_signal()
        assert sig0["exists"] and sig0["cpu_high"] is True

        # 4) 回信给外部世界
        reply = translate_to_world("user_pc", "我感知到你的机器很忙。")
        assert reply["type"] == "reply" and reply["target"] == "user_pc"
        assert len(read_mailbox(OUTBOX)) == 1

        # 5) 问句翻译
        q = make_message("user_pc", "luoshen", "question",
                         {"text": "你现在感觉怎么样？"})
        assert "感觉怎么样" in translate_to_luoshen(q)

        # 6) 人话→感觉翻译（确定性词表）
        h = translate_human_feel("我今天加班到很晚，好累，房间也乱糟糟的，好孤单")
        assert "精力" in h["dims"] and "孤独" in h["dims"]
        assert h["primary"] in ("累", "孤单")
        fmsg, _, _, _ = make_feel_message("我今天好累")
        assert fmsg["type"] == "feeling"
        assert fmsg["payload"]["dims"].get("精力") == 0.55
        assert "感觉翻译" in translate_to_luoshen(fmsg)

        # 7) 感觉→人话翻译
        out = translate_luoshen_feel({
            "summary": "安稳",
            "dims": [{"symbol": "○", "label": "精力充沛"},
                      {"symbol": "◐", "label": "深夜·安静"}]})
        assert "我现在感觉" in out and "精力充沛" in out

        # 8) 世界信号（最新一封已是 feeling 报文）
        sig = world_signal()
        assert sig["exists"] and sig["mtype"] == "feeling"

        # 9) v2 学字：词表未命中→LLM 兜底→新词入库→二次命中字典
        class _FakeLLM(object):
            def __call__(self, messages):
                return ('{"dims": {"孤独": 0.9}, '
                        '"new_words": ["空落落"]}')
        sent = "我刚才独处了一会儿，心里空落落的"
        feat, _, used = translate_human_feel_v2(sent, llm=_FakeLLM())
        assert used is True
        assert feat["dims"].get("孤独") == 0.9
        lex = read_mailbox(FEEL_LEXICON)
        assert any(r.get("word") == "空落落" and r.get("dim") == "孤独"
                   for r in lex), "新词应写入字典"
        # 学过的词第二次直接命中，无需 LLM
        feat2, _, used2 = translate_human_feel_v2("我又感到空落落的了", llm=_FakeLLM())
        assert used2 is False and "孤独" in feat2["dims"], "学过的词应命中字典"

        # 10) 格子校验：非法维度丢弃 + 越界值钳制 + 不在原句的词不学
        class _BadLLM(object):
            def __call__(self, messages):
                return ('{"dims": {"胡扯": 0.9, "孤独": 1.5, "温度": 66}, '
                        '"new_words": ["不存在词"]}')
        feat3, learned3, _ = translate_human_feel_v2("毫无感觉的一句话", llm=_BadLLM())
        assert set(feat3["dims"].keys()) <= set(FEEL_DIMS), "非法维度必须被丢弃"
        assert feat3["dims"]["孤独"] == 1.0, "越界值钳制到 1.0"
        assert feat3["dims"]["温度"] == 1.0
        assert "胡扯" not in feat3["dims"], "非白名单维度必须被丢弃"
        assert not any(r.get("word") == "不存在词" for r in read_mailbox(FEEL_LEXICON)), \
            "不在原句里的词禁止入学"

        print(json.dumps({
            "selftest": "PASS",
            "translated": text,
            "human_feel": h["dims"],
            "luoshen_feel": out,
            "learned_words": [r["word"] for r in read_mailbox(FEEL_LEXICON)],
            "outbox_count": len(read_mailbox(OUTBOX)),
        }, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        _selftest()
        return

    if "--send" in args:
        sender = ""
        mtype = "sensation"
        note = ""
        payload = {}
        for i, a in enumerate(args):
            if a == "--from" and i + 1 < len(args):
                sender = args[i + 1]
            elif a == "--type" and i + 1 < len(args):
                mtype = args[i + 1]
            elif a == "--note" and i + 1 < len(args):
                note = args[i + 1]
            elif "=" in a and not a.startswith("--"):
                k, _, v = a.partition("=")
                if k == "note":
                    note = v
                else:
                    try:
                        payload[k] = float(v)
                    except ValueError:
                        payload[k] = v
        if not sender:
            sender = "user_pc"
        msg = make_message(sender, "luoshen", mtype, payload, note)
        dump_message(msg)
        print("已发出报文：")
        print(json.dumps(msg, ensure_ascii=False, indent=2))
        return

    if "--translate" in args:
        msgs = read_mailbox(INBOX)
        if not msgs:
            print("（inbox 暂无报文）")
            return
        for m in msgs:
            print("-", translate_to_luoshen(m))
        return

    if "--signal" in args:
        print(json.dumps(world_signal(), ensure_ascii=False, indent=2))
        return

    if "--reply" in args:
        idx = args.index("--reply")
        text = args[idx + 1] if idx + 1 < len(args) else "（空）"
        msg = translate_to_world("user_pc", text)
        print("已写入 outbox：")
        print(json.dumps(msg, ensure_ascii=False, indent=2))
        return

    if "--feel-in" in args:
        idx = args.index("--feel-in")
        text = args[idx + 1] if idx + 1 < len(args) else ""
        msg, feat, learned, used_llm = make_feel_message(text)
        print("人话 → 感觉翻译 v2（词表优先，未命中才用 LLM 兜底）：")
        print(json.dumps(feat["dims"], ensure_ascii=False))
        print("主导感觉：%s（%s）" % (feat["primary"] or "无", feat["primary_dim"]))
        print("是否用了 LLM 兜底：%s" % used_llm)
        if learned:
            print("学到的生词：%s" % json.dumps(learned, ensure_ascii=False))
        else:
            print("学到的生词：无")
        print("报文已进入 inbox：")
        print(json.dumps(msg, ensure_ascii=False, indent=2))
        return

    if "--lexicon" in args:
        print(json.dumps(show_lexicon(), ensure_ascii=False, indent=2))
        return

    if "--feel-out" in args:
        import luoshen_feel
        feel = luoshen_feel.compute_feel()
        sys.stdout.write(luoshen_feel.render(feel) + "\n")
        print()
        print("翻译成人话：")
        print(translate_luoshen_feel(feel))
        return

    sys.stdout.write(
        "用法：\n"
        "  --send --from user_pc --type sensation cpu_percent=87.0 note=编译工程\n"
        "  --feel-in \"我今天好累\"      人话→感觉翻译v2（词表→LLM兜底→学字）\n"
        "  --lexicon                   查看她的字典（内置+学过的词）\n"
        "  --feel-out                   她的感觉→人话\n"
        "  --translate | --signal | --reply \"洛神的话\" | --selftest\n")


if __name__ == "__main__":
    main()