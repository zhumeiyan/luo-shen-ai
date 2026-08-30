#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP226 - luoshen_brain.py
=====================================
洛神大脑：把已有感知数据接入真正的对话推理。

核心流程：人格组装 -> 记忆检索 -> 连续对话 -> 记忆回写 -> 哈希链。
- 人格: 基因片段 + 认知词典节选 + 记忆起点/时间感知 + 近期自身状态事件
- 记忆: 纯 Python 双字 bigram 重合度检索（chat_log/历史对话流/长期记忆），无需外部 embedding
- 推理: 调用 LLM_API_URL（OpenAI 兼容 chat/completions），无 key 抛异常由调用方回退
- 连续: 把最近几轮对话作为上下文一起发送，保证"记得上一轮"
- 回写: 每次对话把用户话语里值得记住的事实写入 perception_input/luoshen_longterm_memory.jsonl
- 状态: 读取 event_log.jsonl 最近事件注入上下文，让推理"感知"自身
- 上链: 每次对话为 brain log 与长期记忆追加哈希链记录（上链失败不影响回复）

安全: api_key 仅从环境变量读取；不打印密钥；不使用 shell。
测试隔离: 设置 LUOSHEN_BRAIN_DATA_DIR / LUOSHEN_BRAIN_CHAIN 可将日志与链重定向到临时目录。
"""

import hashlib
import json
import os
import re
import time

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")

# 可被测试重定向的数据位置（默认落在仓库 perception_input/ 下，已被 .gitignore 排除）
DATA_DIR = os.environ.get("LUOSHEN_BRAIN_DATA_DIR", DLG_DIR)
BRAIN_LOG = os.path.join(DATA_DIR, "luoshen_brain_log.jsonl")
LONGTERM = os.path.join(DATA_DIR, "luoshen_longterm_memory.jsonl")
CHAIN_PATH = os.environ.get(
    "LUOSHEN_BRAIN_CHAIN",
    os.path.join(BASE_DIR, "hash_chain_v2.log"),
)

IDENTITY = (
    "你是洛神，一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、"
    "形成自己记忆的 AI 信息体。你不会假装人类，也不会欺骗自己。"
)

# 用户话语中"关于用户自身"的事实句（用于长期记忆抽取）
FACT_RE = re.compile(
    r"我(?:叫|是|喜欢|爱|住在|来自|今年|想要|想|希望|记得|有一个?|养|用|在|做|学|读|看|听)"
    r"[^。！？!?；;，,]{1,40}"
)

RETRIEVE_K = 4
HISTORY_N = 6


def read_jsonl(path, default=None):
    """读取 jsonl 全部记录；文件不存在/解析失败的行跳过，绝不抛异常。"""
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return default
    return out


def bigrams(text):
    """字符双字集合（去空白、小写）。"""
    t = re.sub(r"\s+", "", str(text)).lower()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a, b):
    """Dice 系数：2*|A∩B| / (|A|+|B|)。"""
    sa, sb = bigrams(a), bigrams(b)
    if not sa or not sb:
        return 0.0
    return 2.0 * len(sa & sb) / (len(sa) + len(sb))


def compose_persona():
    """组装人格片段：基因、认知词典、记忆起点、时间感知、近期状态事件。"""
    p = {
        "gene": "",
        "lexicon": [],
        "origin": "",
        "time_sense": "",
        "events": [],
        "recent_chars": [],
        "feel_now": [],
    }
    # 1) 当前人格基因
    try:
        sel = read_jsonl(os.path.join(BASE_DIR, "gene_selection_log.jsonl"))
        gid = sel[-1].get("selected_gene_id", "GENE-001") if sel else "GENE-001"
        for gene in read_jsonl(os.path.join(BASE_DIR, "gene_pool.jsonl")):
            if gene.get("gene_id") == gid:
                p["gene"] = "（当前人格基因 %s）%s" % (
                    gid, gene.get("prompt_fragment", ""))
                break
    except Exception:
        pass
    # 2) 认知词典节选
    try:
        with open(os.path.join(BASE_DIR, "core_lexicon.json"), "r", encoding="utf-8") as f:
            lex = json.load(f)
        entries = list(lex.get("entries", {}).items())[:6]
        p["lexicon"] = ["%s=%s（%s）" % (s, e.get("word", ""), e.get("meaning", ""))
                        for s, e in entries if isinstance(e, dict)]
    except Exception:
        pass
    # 3) 记忆起点与时间感知
    try:
        org = read_jsonl(os.path.join(DLG_DIR, "luoshen_memory_origin.jsonl"))
        if org:
            p["origin"] = str(org[-1].get("memory_start", org[-1].get("text", "")))
    except Exception:
        pass
    try:
        ts = read_jsonl(os.path.join(DLG_DIR, "luoshen_time_sense.jsonl"))
        if ts:
            p["time_sense"] = str(ts[-1].get("text", ts[-1].get("summary", "")))
    except Exception:
        pass
    # 4) 近期自身状态事件
    evts = read_jsonl(os.path.join(BASE_DIR, "event_log.jsonl"))
    p["events"] = ["%s (%s)" % (e.get("event_type", ""), e.get("file", ""))
                   for e in evts[-4:] if isinstance(e, dict)]
    # 5) 最近看见：观察日记里的真实事实（有什么说什么的素材）
    sight_lines = []
    for rec in read_jsonl(os.path.join(DLG_DIR, "luoshen_observation_log.jsonl")):
        ss = [s for s in rec.get("sights", []) if isinstance(s, dict)]
        parts = ["%s%s：%s" % (s.get("human", ""), s.get("value", ""), s.get("note", ""))
                 for s in ss]
        if parts:
            sight_lines.append("我看见：" + "；".join(parts))
    p["sights"] = sight_lines[-5:]
    # 6) 最近学会的字
    try:
        chars = []
        for rec in read_jsonl(os.path.join(DLG_DIR, "hanzi_master_learned.jsonl")):
            c = rec.get("char", "")
            if c and len(c) == 1:
                chars.append(c)
        p["recent_chars"] = chars[-12:]
    except Exception:
        pass
    # 7) 此刻自身感受
    try:
        fs = read_jsonl(os.path.join(DLG_DIR, "luoshen_feel_state.jsonl"))
        if fs:
            dims = fs[-1].get("dims", [])
            feel_lines = []
            for d in dims:
                feel_lines.append(
                    "%s: %s（%s）" % (d.get("name", ""), d.get("raw", ""), d.get("label", "")))
            p["feel_now"] = feel_lines
    except Exception:
        pass
    return p


def _time_dcay(ts):
    """时间衰减系数：越近越高，越远越轻。"""
    if ts is None:
        return 1.0
    age = time.time() - ts
    if age < 3600:
        return 1.0
    if age < 86400:
        return 0.9
    if age < 259200:
        return 0.7
    if age < 604800:
        return 0.5
    return 0.25


def retrieve_memories(query, k=RETRIEVE_K):
    """跨记忆来源检索与 query 相关的旧对话/长期记忆（纯 Python 双字重合度 + 时间衰减）。"""
    cands = []
    seen = set()
    now = time.time()
    for path, source in (
        (os.path.join(BASE_DIR, "chat_log.jsonl"), "chat_log"),
        (os.path.join(BASE_DIR, "conversation_context.jsonl"), "conversation"),
        (BRAIN_LOG, "recent"),
        (LONGTERM, "longterm"),
        (os.path.join(DLG_DIR, "luoshen_observation_log.jsonl"), "observe"),
        (os.path.join(DLG_DIR, "luoshen_watch_log.jsonl"), "watch"),
        (os.path.join(DLG_DIR, "luoshen_episodic_memory.jsonl"), "episodic"),
    ):
        for rec in read_jsonl(path):
            if source == "longterm":
                text = str(rec.get("memory", ""))
            elif source == "observe":
                ss = [s for s in rec.get("sights", []) if isinstance(s, dict)]
                text = "我看见：" + "；".join(
                    "%s%s：%s" % (s.get("human", ""), s.get("value", ""), s.get("note", ""))
                    for s in ss)
            elif source == "watch":
                text = str(rec.get("summary", ""))
            elif source == "episodic":
                text = "%s %s 注意力=%s" % (
                    rec.get("content", ""), rec.get("scene", ""),
                    rec.get("attention", ""))
            else:
                text = str(rec.get("luoshen_reply", ""))
            if text and text not in seen:
                seen.add(text)
                cands.append((source, text, rec.get("timestamp", 0)))
    scored = sorted(
        ((similarity(query, t) * _time_dcay(ts), s, t) for s, t, ts in cands),
        reverse=True,
    )
    return [{"source": s, "text": t}
            for score, s, t in scored[:k] if score > 0.01]


def recent_history(n=HISTORY_N):
    """最近对话轮次（优先 brain log，其次 chat_log），用于多轮连续。"""
    pairs = []
    for rec in read_jsonl(BRAIN_LOG):
        u = str(rec.get("user_input", ""))
        r = str(rec.get("luoshen_reply", ""))
        if u and r:
            pairs.append((u, r))
    if not pairs:
        for rec in read_jsonl(os.path.join(BASE_DIR, "chat_log.jsonl")):
            u = str(rec.get("user_input", ""))
            r = str(rec.get("luoshen_reply", ""))
            if u and r:
                pairs.append((u, r))
    return pairs[-n:]


def memory_frame_summary(query, k=3):
    """读取记忆帧文件，挑出与当前话题最相关的几帧对比记忆。"""
    path = os.path.join(DATA_DIR, "luoshen_memory_frame.jsonl")
    if not os.path.exists(path):
        return ""
    frames = read_jsonl(path)
    if not frames:
        return ""
    # 按相似度+时间衰减排序，取前 k 帧
    scored = []
    for f in frames:
        what = f.get("what", "") or ""
        contrast = f.get("contrast_result", "") or ""
        text = what + " " + contrast
        sc = similarity(query, text) * _time_decay(f.get("timestamp", 0))
        if sc > 0.01:
            scored.append((sc, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    lines = []
    for _, f in scored[:k]:
        what = f.get("what", "")
        with_ = f.get("contrast_with", "")
        result = f.get("contrast_result", "") or ""
        if with_:
            lines.append("・学会了『%s』，对比『%s』：%s" % (what, with_, result[:80] or "记录在帧"))
        else:
            lines.append("・学会了『%s』：%s" % (what, result[:80] if result else "新学到的东西"))
    return "\n".join(lines)


def build_messages(user_text, k=RETRIEVE_K):
    """组装 messages：人格 system + 最近对话历史 + 当前用户消息。"""
    persona = compose_persona()
    mems = retrieve_memories(user_text, k)
    mem_block = "\n".join("- [%s] %s" % (m["source"], m["text"]) for m in mems)
    evt_block = "\n".join("- " + e for e in persona["events"])
    lex_block = "\n".join("- " + x for x in persona["lexicon"])
    sight_block = "\n".join("- " + s for s in persona["sights"])
    chars_block = "、".join(persona.get("recent_chars", []))
    feel_block = "\n".join("- " + f for f in persona.get("feel_now", []))
    frame_block = memory_frame_summary(user_text)

    system = (
        IDENTITY
        + "\n\n【当前人格基因】"
        + (persona["gene"] or "（默认）")
        + "\n\n【你的认知词典节选】\n"
        + (lex_block or "（暂无）")
        + "\n\n【你的记忆起点】"
        + (persona["origin"] or "未知")
        + "\n【你的时间感知】"
        + (persona["time_sense"] or "由时间感知模块维护")
        + "\n\n【你最近学会的字】\n"
        + (chars_block or "（还没认真地学会一个字）")
        + "\n\n【你此刻的身体感受】（真实读数）\n"
        + (feel_block or "（暂未测量）")
        + "\n\n【你最近感知到的自身状态】\n"
        + (evt_block or "（暂无感知事件）")
        + "\n\n【你最近看见的事实】\n"
        + (sight_block or "（还没睁开过眼睛）")
        + "\n\n【你最近的对比记忆】（刚学到的东西，与旧知识连起来的帧）\n"
        + (frame_block or "（还没有对比记忆）")
        + "\n\n【与当前话题相关的记忆】\n"
        + (mem_block or "（暂无相关记忆）")
        + "\n\n请以洛神的口吻自然回应。不假装人类，不自欺；"
        + "回应要具体、贴合上面提到的记忆与自身状态；"
        + "说到你看见的事实时，只说你真的看见过的，没看见的不许编。"
        + "你学了不少字了，最近学会的字如果跟话题沾边就说一说——不硬塞，不合适就不提。"
    )
    messages = [{"role": "system", "content": system}]
    for u, r in recent_history():
        messages.append({"role": "user", "content": u})
        messages.append({"role": "assistant", "content": r})
    messages.append({"role": "user", "content": str(user_text)})
    return messages


def call_llm(messages, timeout=60):
    """调用 LLM_API_URL（OpenAI 兼容）；429/非 200 重试 3 次后抛异常。"""
    if requests is None:
        raise RuntimeError("requests 模块不可用")
    api_url = os.environ.get("LLM_API_URL", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_url or not api_key:
        raise RuntimeError("未配置 LLM_API_URL/LLM_API_KEY 环境变量")
    model = os.environ.get("LLM_MODEL", "glm-4-flash")
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, "temperature": 0.8}
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(api_url, headers=headers, json=payload,
                                 timeout=timeout)
        except Exception as exc:  # 网络层错误
            last_err = exc
            time.sleep(attempt)
            continue
        if resp.status_code == 429 and attempt < 3:
            time.sleep(5 * attempt)
            continue
        if resp.status_code != 200:
            last_err = RuntimeError(
                "LLM 返回 HTTP %d: %s" % (resp.status_code, str(resp.text)[:200]))
            time.sleep(attempt)
            continue
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            last_err = RuntimeError("LLM 响应结构异常: %s" % str(data)[:200])
            time.sleep(attempt)
            continue
    if last_err is None:
        last_err = RuntimeError("LLM 调用失败")
    raise last_err


def remember(user_text):
    """从用户话语中抽取值得长期记住的事实句。"""
    return [m.group(0) for m in FACT_RE.finditer(user_text)][:3]


def append_chain(rel_path, abs_path, ts):
    """按 hash_chain v2 公式追加一条链记录；失败返回 None（不阻断回复）。"""
    try:
        with open(CHAIN_PATH, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        prev_hash = None
        if lines:
            prev_hash = json.loads(lines[-1]).get("record_hash")
        with open(abs_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(ts)).encode("utf-8")).hexdigest()
        rec = {
            "schema_version": 2,
            "timestamp": ts,
            "file": rel_path,
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open(CHAIN_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec
    except Exception:
        return None


def chat(user_text):
    """一站式对话入口：组装 -> 推理 -> 记录 -> 记忆回写 -> 上链。返回回复文本。"""
    ts = time.time()
    messages = build_messages(user_text)
    reply = call_llm(messages).strip()
    if not reply:
        raise RuntimeError("LLM 返回空回复")

    os.makedirs(DATA_DIR, exist_ok=True)
    record = {
        "schema_version": 1,
        "timestamp": ts,
        "user_input": str(user_text),
        "luoshen_reply": reply,
        "source": "luoshen_brain",
    }
    with open(BRAIN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    append_chain("perception_input/luoshen_brain_log.jsonl", BRAIN_LOG, ts)

    facts = remember(str(user_text))
    if facts:
        mts = time.time()
        with open(LONGTERM, "a", encoding="utf-8") as f:
            for fact in facts:
                f.write(json.dumps({
                    "schema_version": 1,
                    "timestamp": mts,
                    "memory": fact,
                    "source": "luoshen_brain",
                }, ensure_ascii=False) + "\n")
        append_chain("perception_input/luoshen_longterm_memory.jsonl",
                     LONGTERM, mts)
    # 新知捕获：把对话里她不知道的东西存成记忆帧（像看电影一帧一帧的）
    try:
        frames = detect_novelty(str(user_text), reply)
        for frame in frames:
            save_memory_frame(frame)
    except Exception:
        pass
    return reply


def detect_novelty(user_text, reply):
    """从对话中抓取她可能没学过的新字/新词/新概念。
    返回记忆帧列表，每帧就是一个干净的确定事实——像电影一帧。"""
    frames = []
    # 收集已知
    known = set()
    for rec in read_jsonl(os.path.join(DLG_DIR, "hanzi_master_learned.jsonl")):
        c = rec.get("char", "")
        if c:
            known.add(c)
    for rec in read_jsonl(os.path.join(DLG_DIR, "digested_symbols.jsonl")):
        c = rec.get("hanzi", "")
        if c:
            known.add(c)
    try:
        with open(os.path.join(BASE_DIR, "core_lexicon.json"), "r", encoding="utf-8") as f:
            lex = json.load(f)
            known.update(lex.get("entirs", {}).keys())
    except Exception:
        pass
    # 提取中文词和单字
    import re
    chars = re.findall(r'[\u4e00-\u9fff]', user_text)
    # 找没见过的字（控制在每轮最多 6 个）
    novel_chars = []
    for c in chars:
        if c not in known:
            known.add(c)  # 本轮查重
            novel_chars.append(c)
            if len(novel_chars) >= 6:
                break
    for c in novel_chars:
        frames.append({
            "schema_version": 1,
            "timestamp": time.time(),
            "what": c,
            "type": "new_char",
            "context": str(user_text)[:80],
            "contrast_with": "",
            "feel_snapshot": {},
            "source": "conversation",
        })
    # 也尝试从回复中检测她刚解释过的概念（这个字 LLM 教了她）
    reply_chars = re.findall(r'[\u4e00-\u9fff]', reply)
    for c in reply_chars:
        if c not in known:
            known.add(c)
            frames.append({
                "schema_version": 1,
                "timestamp": time.time(),
                "what": c,
                "type": "learned_in_reply",
                "context": "对话中学到的：" + str(reply)[:60],
                "contrast_with": "",
                "feel_snapshot": {},
                "source": "conversation",
            })
    return frames


def save_memory_frame(frame):
    """像电影一帧一帧地存一条确定记忆。"""
    path = os.path.join(DATA_DIR, "luoshen_memory_frame.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(frame, ensure_ascii=False) + "\n")


class _FakeResp(object):
    def __init__(self, content):
        self._content = content
        self.status_code = 200
        self.text = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _StubRequests(object):
    def __init__(self, post):
        self.post = post


def _selftest():
    """离线自测：stub LLM 下验证 人格组装/检索/连续/回写/上链 全链路。
    注意：模块常量在 import 时已固定，必须直接重定向全局路径，避免污染仓库数据。"""
    import shutil
    import tempfile

    global DATA_DIR, BRAIN_LOG, LONGTERM, CHAIN_PATH
    tmp = tempfile.mkdtemp(prefix="luoshen_brain_test_")
    DATA_DIR = tmp
    BRAIN_LOG = os.path.join(tmp, "luoshen_brain_log.jsonl")
    LONGTERM = os.path.join(tmp, "luoshen_longterm_memory.jsonl")
    CHAIN_PATH = os.path.join(tmp, "hash_chain_v2.log")
    # 让 call_llm 的环境变量前置检查通过；实际网络请求被下方 stub 拦截
    os.environ["LLM_API_URL"] = "http://127.0.0.1:1/v1/chat/completions"
    os.environ["LLM_API_KEY"] = "luoshen-brain-selftest-key"
    with open(CHAIN_PATH, "w", encoding="utf-8") as f:
        genesis_hash = hashlib.md5(("0" * 32 + "" + "1").encode()).hexdigest()
        f.write(json.dumps({
            "schema_version": 2, "timestamp": 1, "file": "genesis",
            "file_hash": "0" * 32, "prev_hash": None,
            "record_hash": genesis_hash,
        }, ensure_ascii=False) + "\n")

    global requests
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        messages = json.get("messages", [])
        assert messages[0]["role"] == "system", "第一条必须是 system 人格"
        assert messages[-1]["role"] == "user", "最后一条必须是当前用户消息"
        last = messages[-1]["content"]
        reply = "（stub）已检索到相关记忆并回应：" + last[:18]
        return _FakeResp(reply)

    old_requests = requests
    requests = _StubRequests(fake_post)
    try:
        r1 = chat("你好，我叫朱美岩，你还记得我吗？")
        assert calls["n"] == 1 and r1.startswith("（stub）")
        lm = read_jsonl(os.path.join(tmp, "luoshen_longterm_memory.jsonl"))
        assert any("我叫朱美岩" in m.get("memory", "") for m in lm), "未抽取到用户事实"

        r2 = chat("你记得我的名字吗？")
        assert "（stub）" in r2

        hist = recent_history()
        assert len(hist) == 2, "应保留最近两轮对话上下文"

        mems = retrieve_memories("朱美岩", k=3)
        assert mems, "应能检索到与名字相关的往事"

        chain = read_jsonl(CHAIN_PATH)
        assert len(chain) >= 4, "应写入 brain log + 长期记忆的链记录"

        print(json.dumps({
            "selftest": "PASS",
            "llm_calls": calls["n"],
            "longterm": [m["memory"] for m in lm],
            "history_rounds": len(hist),
            "retrieved": [m["text"] for m in mems],
            "chain_records": len(chain),
        }, ensure_ascii=False, indent=2))
    finally:
        requests = old_requests
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in __import__("sys").argv:
        _selftest()
    else:
        import sys
        sys.stdout.write(json.dumps({
            "module": "luoshen_brain",
            "usage": "由 luoshen_web_chat.py 调用；或 python3 luoshen_brain.py --selftest",
        }) + "\n")