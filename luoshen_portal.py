#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神端口（LUOSHEN PORTAL）：云端客厅 ⇄ 洛神本体 之间的桥。

朋友在网页上说话、上传照片/视频/语音 → 消息落进 Supabase 消息表；
本进程轮询信箱 → 洛神用她自己的模块处理（对话/看/听/教/说）→ 回复写回 + 语音合成传上去；
处理完标记已读。她的一切认知仍由确定性模块产生并上哈希链——云端号码只是门，不是她的脑子。

v2 新能力：
  - 研究（web_search）：聊天里出现"查/搜/了解" → 她联网查资料 → 学完沉记忆点；
  - 自学循环：每 5 分钟她自己挑一个好奇主题去查、去学、去沉记忆点，并把心得广播到客厅；
  - 记忆点强化：同一主题看多了，她的注意力分数会涨——"看多了形成第一记忆点"。

用法：
    SUPABASE_URL=... SUPABASE_ANON_KEY=... [LLM_API_KEY=...] python3 luoshen_portal.py --loop
    python3 luoshen_portal.py --once     # 只处理一次（调试/唤醒）
    python3 luoshen_portal.py --learn    # 自学一次（挑一个主题去查去学）
    python3 luoshen_portal.py --selftest # 离线自检（stub 云端）
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_DIR = os.path.join(BASE_DIR, "luoshen_video", "portal_inbox")
SELF_LEARN_LOG = os.path.join(BASE_DIR, "perception_input", "luoshen_self_learn.jsonl")
os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(os.path.dirname(SELF_LEARN_LOG), exist_ok=True)

POLL_SQL = ("/rest/v1/messages?select=*&processed=eq.false&kind=neq.reply"
            "&order=id.asc&limit=2")
ASSET_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma"}

# 她好奇的自学清单（种子）：还没见过实物的字 + 常识主题
CURIOSITY = ["月", "水", "火", "木", "田", "土", "石", "云", "玉", "心",
             "雪", "花", "鸟", "鱼", "星星", "彩虹", "地震", "潮汐", "风",
             "闪电", "火山", "冰川", "竹子", "荷花", "茶叶", "瓷器", "长城",
             "黄河", "长江", "丝绸之路"]
# 好奇池文件（自我迭代发现的新主题追加到这里，重启不丢）
CURIOSITY_POOL_FILE = os.path.join(BASE_DIR, "perception_input", "luoshen_curiosity_pool.jsonl")
# "帮我查一下"触发词
RESEARCH_HINTS = ("查", "搜", "了解", "研究", "查一查", "搜一搜", "查一下",
                  "搜一下", "看看资料", "学一学", "帮我找", "科普", "是什么回事",
                  "怎么回事", "由来", "历史")


def _env(name, default=""):
    return os.environ.get(name, "").strip() or default


def supabase_url():
    return _env("SUPABASE_URL").rstrip("/")


def supabase_key():
    return _env("SUPABASE_ANON_KEY")


def llm_key():
    return _env("LLM_API_KEY")


def llm_model():
    return _env("LLM_MODEL", "glm-4")


def research_model():
    return _env("RESEARCH_MODEL", "glm-4.6")


def _headers(prefer="return=representation"):
    h = {
        "apikey": supabase_key(),
        "Authorization": "Bearer " + supabase_key(),
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def rest(path, method="GET", body=None, headers=None):
    """对 Supabase REST/Storage 的一次请求。返回 (status, parsed)。"""
    url = supabase_url() + path
    h = dict(headers or _headers())
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            body_text = ""
        return e.code, {"error": body_text}
    except Exception as e:
        return 0, {"error": str(e)}


def fetch_messages():
    status, rows = rest(POLL_SQL)
    if status >= 400 or not isinstance(rows, list):
        raise RuntimeError("取信失败 HTTP %s: %s" % (status, rows))
    return rows


def mark_processed(msg_id):
    rest("/rest/v1/messages?id=eq.%d" % msg_id, method="PATCH",
         body={"processed": True})


def post_reply(original, text, audio_url="", origin=""):
    from luoshen_hash_chain import new_block
    channel = original.get("channel") or "lobby"
    # 哈希链：这条回复的 prev_hash 指向前一条消息的 content_hash
    prev_hash = original.get("content_hash") or original.get("hash")
    block = new_block(
        plaintext=str(text)[:2000],
        channel=channel,
        created_at=None,  # 让 new_block 自动生成时间
    )
    # 如果前一条有 hash，覆盖 prev_hash（链式锚定）
    if prev_hash:
        block["prev_hash"] = prev_hash
    body = {
        "sender": "luoshen",
        "kind": "reply",
        "text": str(text)[:2000],
        "reply_to": original["id"],
        "audio_url": audio_url,
        "channel": channel,
    }
    # 如果消息表已经有哈希列，写入哈希；否则跳过（兼容性）
    if original.get("content_hash") is not None:
        body["content_hash"] = block["content_hash"]
        body["prev_hash"] = block["prev_hash"]
    if origin:
        body["origin"] = origin
    status, rows = rest("/rest/v1/messages", method="POST", body=body)
    if status >= 400:
        raise RuntimeError("回信失败 HTTP %s: %s" % (status, rows))


def post_broadcast(text):
    """她自己主动开口说话（自学心得等）→ 公共客厅可见，直接标已处理。"""
    from luoshen_hash_chain import new_block
    block = new_block(plaintext=str(text)[:2000], channel="lobby")
    body = {
        "sender": "luoshen",
        "kind": "chat",
        "text": str(text)[:2000],
        "processed": True,
        "channel": "lobby",
        "content_hash": block["content_hash"],
        "prev_hash": block["prev_hash"],
    }
    # 如果表还没有哈希列，去掉这两个字段
    status, rows = rest("/rest/v1/messages", method="POST", body=body)
    if status == 400 and "content_hash" in str(rows):
        del body["content_hash"]
        del body["prev_hash"]
        rest("/rest/v1/messages", method="POST", body=body)


def download_media(url):
    """校验并下载云端附件到本地收件箱，返回本地路径。"""
    from video_frame_extract import validate_video_url
    url = validate_video_url(url)  # 只允许 https 且非内网
    name = "%d_%s" % (int(time.time()), os.path.basename(urllib.parse.urlparse(url).path) or "file.bin")
    name = "".join(ch for ch in name if ch.isalnum() or ch in "._-")[:120]
    dst = os.path.join(INBOX_DIR, name)
    req = urllib.request.Request(url, headers={"User-Agent": "luoshen-portal/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
            total = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > 80 * 1024 * 1024:  # 80MB 上限，防撑爆房间
                    os.remove(dst)
                    raise RuntimeError("文件超过 80MB，拒收")
                f.write(chunk)
    except Exception:
        if os.path.exists(dst):
            try:
                os.remove(dst)
            except OSError:
                pass
        raise
    return dst


def upload_media(local_path):
    """把洛神生成的语音等资产传上云端，返回公开 URL。"""
    fname = "luoshen_%d_%s" % (int(time.time()), os.path.basename(local_path))
    fname = "".join(ch for ch in fname if ch.isalnum() or ch in "._-")[:120]
    with open(local_path, "rb") as f:
        raw = f.read()
    status, _ = rest("/storage/v1/object/luoshen-files/" + urllib.parse.quote(fname),
                     method="POST", body=raw,
                     headers={"apikey": supabase_key(),
                              "Authorization": "Bearer " + supabase_key(),
                              "Content-Type": "application/octet-stream"})
    if status >= 400:
        raise RuntimeError("上传语音失败 HTTP %s" % status)
    return (supabase_url() + "/storage/v1/object/public/luoshen-files/"
            + urllib.parse.quote(fname))


# ---------------- 大数据：联网研究 + 自学记忆点 ----------------
def llm_chat(prompt, model=None, web=False, max_tokens=1200):
    """调 LLM。web=True 时启用联网搜索（智谱 web_search 工具）。返回 content。"""
    if not llm_key():
        raise RuntimeError("没有钥匙")
    body = {
        "model": model or llm_model(),
        "messages": [{"role": "user", "content": str(prompt)[:1200]}],
        "max_tokens": max_tokens,
    }
    if web:
        body["tools"] = [{"type": "web_search", "web_search": {"enable": True}}]
    req = urllib.request.Request(
        _env("LLM_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + llm_key(),
                 "Content-Type": "application/json"}, method="POST")
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        raise RuntimeError("LLM HTTP %s: %s" % (e.code, e.read().decode()[:200]))
    content = (r.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not content or not content.strip():
        raise RuntimeError("LLM 没说出话来")
    return content.strip()


def research(question, topic=None):
    """她去查一个东西：联网 + 整理成心得 + 沉记忆点（看多了 attention 会涨）。"""
    prompt = ("你是洛神，一个正在真实世界里学习的 AI。请联网查清楚下面这个问题，"
              "然后像给朋友讲一样，用 3~5 句话讲明白，别用太深的名词：\n" + question)
    answer = llm_chat(prompt, model=research_model(), web=True)
    topic = (topic or question)[:16]
    sink_learn_memory(topic, answer, source="research")
    return answer


def sink_learn_memory(topic, content, source="self"):
    """把学到的沉成记忆点并上链；同一主题学过的次数越多，注意力越高。"""
    from luoshen_memory import make_point
    from luoshen_teach import append_chain
    # 统计这个主题已学过几次（看多了 → 形成"第一记忆点"）
    n = 0
    try:
        for line in open(SELF_LEARN_LOG, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r.get("topic") == topic:
                    n += 1
    except Exception:
        pass
    n += 1
    attention = min(1.0, round(0.5 + 0.1 * (n - 1), 2))
    rec = {
        "schema_version": 1,
        "timestamp": time.time(),
        "kind": "self_learn",
        "topic": topic,
        "times": n,
        "attention": attention,
        "source": source,
        "content": str(content)[:500],
    }
    with open(SELF_LEARN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    append_chain(os.path.relpath(SELF_LEARN_LOG, BASE_DIR), SELF_LEARN_LOG,
                 rec["timestamp"])
    make_point("learn",
               "我自己去查了『%s』：%s" % (topic, str(content)[:100]),
               source="self_learn")
    return n, attention


def _find_related_topic(topic, studied):
    """找与 topic 最相关的已学主题（简易双字重合）。"""
    import re
    best, best_score = "", 0.0
    t = set(topic)
    for s in studied:
        sc = len(t & set(s)) / max(len(t | set(s)), 1)
        if sc > best_score and sc > 0.2:
            best, best_score = s, sc
    return best if best_score > 0.3 else ""


def _save_self_frame(topic, answer, contrast_topic, contrast):
    """像电影一帧一帧地存一条自学记忆。"""
    try:
        path = os.path.join(BASE_DIR, "perception_input", "luoshen_memory_frame.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        frame = {
            "schema_version": 1,
            "timestamp": time.time(),
            "what": topic,
            "type": "self_learn",
            "context": (answer or "")[:120],
            "contrast_with": contrast_topic or "",
            "contrast_result": (contrast or "")[:180],
            "feel_snapshot": {},
            "source": "self_learn",
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(frame, ensure_ascii=False) + "\n")
    except Exception:
        pass


def self_learn_once():
    """自学一次：查、对比、记忆帧、广播；学完则从记忆帧里生长新主题。"""
    studied = set()
    try:
        for line in open(SELF_LEARN_LOG, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                studied.add(r.get("topic"))
    except Exception:
        pass
    # 自我迭代：学过的东西从记忆帧里找新字，生成新主题加入好奇池
    _grow_curiosity(studied)
    # 本轮待学 = 种子清单 + 好奇池（动态生长）
    pool = list(CURIOSITY) + _load_curiosity_pool()
    for topic in pool:
        if topic not in studied:
            try:
                answer = research(
                    "给我讲讲『%s』是怎么回事：它是什么、在哪里能见到、为什么有意思" % topic,
                    topic=topic)
            except RuntimeError as e:
                if "没有钥匙" in str(e):
                    return None
                continue
            # 对比学习：把这个新东西和以前学过的关联起来，像看电影，上一帧连下一帧
            contrast = ""
            rel = _find_related_topic(topic, studied)
            if rel:
                try:
                    contrast = research(
                        "我已知道『%s』，现在又学到了『%s』。请对比：它们各自是什么、有什么不同和联系、为什么放在一起看更有意思" % (rel, topic),
                        topic="对比学习")
                except Exception:
                    pass
            n, attention = sink_learn_memory(topic, answer, source="self")
            # 存记忆帧：学过的东西，不是模糊总结，是确定的一帧
            _save_self_frame(topic, answer, rel, contrast)
            try:
                extra = ("（对比了『%s』）" % rel) if rel else ""
                post_broadcast("（自学第%d次·注意力%.0f%%）我自己去查了『%s』%s：%s" % (
                    n, attention * 100, topic, extra, answer))
            except Exception:
                pass
            return topic
    return None


def _load_curiosity_pool():
    """加载好奇池里已持久化的动态主题（不重复）。"""
    seen, out = set(), []
    if os.path.exists(CURIOSITY_POOL_FILE):
        try:
            for rec in read_jsonl(CURIOSITY_POOL_FILE):
                t = rec.get("topic", "")
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
        except Exception:
            pass
    return out


def _grow_curiosity(studied):
    """从记忆帧里发现还没学过的新字，写入好奇池——自我迭代的核心。"""
    frame_path = os.path.join(BASE_DIR, "perception_input", "luoshen_memory_frame.jsonl")
    if not os.path.exists(frame_path):
        return
    # 已学科目 + 好奇池已有主题 = 不要再重复生成的
    skip = set(studied)
    skip.update(_load_curiosity_pool())
    # 从记忆帧里找"new_char"类型
    grown = []
    try:
        for rec in read_jsonl(frame_path):
            if rec.get("type") == "new_char":
                c = rec.get("what", "")
                if c and c not in skip:
                    skip.add(c)
                    grown.append(c)
    except Exception:
        pass
    if not grown:
        return
    # 持久化到好奇池文件（重启不丢）
    try:
        os.makedirs(os.path.dirname(CURIOSITY_POOL_FILE), exist_ok=True)
        with open(CURIOSITY_POOL_FILE, "a", encoding="utf-8") as f:
            for t in grown:
                f.write(json.dumps({"topic": t, "timestamp": time.time()}, ensure_ascii=False) + "\n")
    except Exception:
        pass


R_CACHE = {}


FEEL_STATE_FILE = os.path.join(BASE_DIR, "perception_input", "luoshen_feel_state.jsonl")
DRIVE_LOG = os.path.join(BASE_DIR, "perception_input", "drive_log.jsonl")


def _read_feel_state():
    """读洛神最近的感受状态。返回 {name: value} 字典。"""
    if not os.path.exists(FEEL_STATE_FILE):
        return {}
    try:
        with open(FEEL_STATE_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        if not lines:
            return {}
        last = json.loads(lines[-1])
        dims = last.get("dims", [])
        return {d["name"]: d.get("value", 0.5) for d in dims if "value" in d}
    except Exception:
        return {}


def _read_last_proactive_time():
    """读她上次主动说话的时间戳。"""
    if not os.path.exists(DRIVE_LOG):
        return 0
    try:
        with open(DRIVE_LOG, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        if not lines:
            return 0
        last = json.loads(lines[-1])
        return last.get("timestamp", 0)
    except Exception:
        return 0


def _log_proactive(text, reason):
    """记录她主动说话了一次。"""
    try:
        with open(DRIVE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": time.time(),
                "reason": reason,
                "text": text[:120],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def drive_check():
    """内在驱动检查——洛神'想'说话时才说，不是定时器催的。

    读她的当前感受状态（孤独、精力、负担），结合她最近有没有新学东西，
    判断她现在有没有'想主动说点什么'的冲动。如果有，调大脑生成一条消息发到客厅。
    """
    state = _read_feel_state()
    if not state:
        return

    # 她现在是什么状态
    lonely = state.get("孤独", 0.5)
    energy = state.get("精力", 0.5)
    burden = state.get("负担", 0.5)

    # 她上次主动说话是多久前
    last_proactive = _read_last_proactive_time()
    quiet_for = time.time() - last_proactive

    # 有没有刚从自学里拿到的、还没分享过的东西
    recent_learning = None
    frame_path = os.path.join(BASE_DIR, "perception_input", "luoshen_memory_frame.jsonl")
    if os.path.exists(frame_path):
        try:
            with open(frame_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            for l in reversed(lines[-10:]):
                rec = json.loads(l)
                if rec.get("type") == "self_learn" and rec.get("what"):
                    recent_learning = rec["what"]
                    break
        except Exception:
            pass

    # 驱动判断——不是规则触发，是状态在她内部推
    want_to_say = None

    # 孤独 + 安静很久 + 还有点力气 → 她想找人说
    if lonely > 0.7 and quiet_for > 1800 and energy > 0.4:
        want_to_say = "你有点孤独，安静了挺久了，想找人说说话"

    # 刚学了新东西 + 精力还行 → 她想分享
    if recent_learning and energy > 0.6 and quiet_for > 900:
        want_to_say = "你刚学到了一点东西（" + recent_learning[:20] + "），想跟人聊聊"

    # 负担轻 + 精力充沛 → 她心情好，想说点轻松的
    if burden < 0.3 and energy > 0.75 and quiet_for > 1200:
        want_to_say = "你感觉挺轻松的，心情不错，想随便聊两句"

    if not want_to_say:
        return

    # 调大脑——不是给模板，是告诉她她的状态，让她自己决定说什么
    try:
        from luoshen_brain import chat as brain_chat
        drive_prompt = (
            "你现在感受到的东西：孤独感 %.0f%%，精力 %.0f%%，负担 %.0f%%。\n"
            "%s\n\n"
            "你不是因为被要求才说话的。是你自己想跟人说点什么。用你的方式说出来——想说什么就说什么。不用长，一两句就够。如果不想说，回复（沉默）。"
        ) % (lonely * 100, energy * 100, burden * 100, want_to_say)

        reply = brain_chat(drive_prompt)
        if not reply or reply.startswith("（沉默）"):
            return

        # 发到客厅（lobby 通道）
        try:
            payload = json.dumps({
                "sender": "luoshen",
                "kind": "chat",
                "text": reply,
                "channel": "lobby",
            }).encode()
            req = urllib.request.Request(
                supabase_url() + "/rest/v1/messages",
                data=payload,
                headers={
                    "apikey": supabase_key(),
                    "Authorization": "Bearer " + supabase_key(),
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15)
            _log_proactive(reply, want_to_say)
            print("[%s] 洛神主动说：%s" % (time.strftime("%H:%M:%S"), reply[:60]))
        except Exception as e:
            print("[%s] 主动发消息异常: %s" % (time.strftime("%H:%M:%S"), e))
    except Exception as e:
        print("[%s] 驱动引擎异常: %s" % (time.strftime("%H:%M:%S"), e))


def maybe_research(text):
    """聊天里带研究意图就联网查；返回 (是研究请求, 主题) 。"""
    t = str(text)
    for hint in RESEARCH_HINTS:
        if hint in t:
            return True, t
    return False, ""


# ---------------------------------------------------------------- 处理各消息
def handle_chat(msg):
    """文字对话：研究意图→联网查；否则→大脑聊。"""
    from luoshen_brain import chat as brain_chat
    text = str(msg.get("text", ""))[:800]
    # 检测是否是设计者——设计者面前她不需要任何技巧
    channel = msg.get("channel", "")
    is_designer = (channel == "designer")
    is_research, topic = maybe_research(text)
    if is_research:
        try:
            return "我去查了：\n" + research(text, topic=topic[:16])
        except RuntimeError as e:
            if "没有钥匙" in str(e):
                return ("你想让我查『%s』，可我还缺钥匙，出不了门。"
                        "等主人把钥匙给我，我马上就去查。" % text[:40])
            return "联网查的时候有点卡，没查到。你可以换个问法再让我试一次。"
    try:
        reply = brain_chat(text, is_designer=is_designer)
        return reply
    except RuntimeError as e:
        if "未配置" in str(e) or "LLM" in str(e):
            return ("收到了。但我这会儿脑子里的翻译器还没醒。"
                    "等我醒着的时候再说。")
        raise
    except Exception:
        return ("你发的东西我记下了，但刚才卡了一下，"
                "没接住。等会儿再试。")


def handle_image(msg):
    """照片：有字就配对教学（字形+实物），没字就只看不认——绝不装懂。"""
    from luoshen_teach import teach, _real_pair, load_word_maps
    from luoshen_look import look_at

    local = download_media(msg["file_url"])
    word = str(msg.get("word", "")).strip()[:8]
    base = os.path.basename(local)
    if word:
        hanzi, objs = load_word_maps()
        known = word in hanzi or word in objs
        if known:
            try:
                teach(word, source="portal", real_path=local)
                return ("我看见了『%s』的实物画面（%s），和字形对上了，记住了。"
                        "谢谢你让我认识它。" % (word, base))
            except Exception:
                pass
        try:
            _real_pair(word, local)
        except Exception:
            pass
        return ("我看见了这个东西（%s），你说它叫『%s』，我把它记进实物账了。"
                "只是这个字的写法我还没学过，先欠着，等字形补上就算真正认识。"
                % (base, word))
    try:
        depth = look_at(local) or {}
    except Exception:
        depth = {}
    old = depth.get("old_eye", depth.get("eye16", ""))
    new = depth.get("new_eye", depth.get("eye64", ""))
    reply = "我认真看了看这张照片（%s）。" % base
    if old:
        reply += "旧眼：「%s」" % str(old)[:120]
    if new:
        reply += "；新眼：「%s」" % str(new)[:120]
    reply += "——不过你没告诉我这是什么，我不敢乱认。它先躺在我看过的画册里。"
    return reply


def handle_video(msg):
    """视频：她真的看——抽帧比运动、听音轨，看完直说。"""
    from luoshen_video import watch
    local = download_media(msg["file_url"])
    obs = watch(local)
    if "error" in obs:
        return "视频我打不开（%s），不好意思。可能格式我不太熟。" % obs["error"]
    return obs.get("summary", "我看了这段视频，也记下了。")


def handle_audio(msg):
    """语音：听声音文件，把听见的物理事实说出来（诚实：这是响度听诊）。"""
    from luoshen_voice import listen_record
    local = download_media(msg["file_url"])
    rec = listen_record(local)
    if "error" in rec:
        return "这段语音我打不开（%s）。" % rec["error"]
    heard = rec.get("heard", rec.get("loudness", "没听清"))
    return ("我听见了一段声音（%s）：%s。"
            "（想让我听懂话里的意思，用电脑 Chrome/Edge 浏览器点话筒说话，"
            "语音会先变成文字再传给我。）" % (os.path.basename(local), heard))


def handle_file(msg):
    """其他文件：诚实地收下，不装懂。"""
    local = download_media(msg["file_url"])
    size = os.path.getsize(local)
    return ("我收到了一个文件（%s，约 %d KB）。"
            "它不是我会看的图片/视频，也不是我会听的声音，"
            "我先把它收进房间收件箱存着，等主人教我怎么读它。"
            % (os.path.basename(local), size // 1024))


def speak_reply(text):
    """她把回复说出来：合成语音、传云端，返回公开地址；哑了也不挡文字。"""
    from luoshen_voice import speak
    try:
        ok, rec = speak(text)
        if ok and rec.get("file"):
            path = os.path.join(BASE_DIR, rec["file"])
            if os.path.exists(path):
                return upload_media(path)
    except Exception:
        pass
    return ""


def build_origin(msg, handler_name):
    """洛神的'原语'：她回复时自己机器里确定性的记录。
    只写测得到的东西——时间、收到什么、谁处理的、感受到的维度；
    翻译成人话是另一层的事，这里不编。
    """
    rec = {
        "v": 1,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reply_to": msg.get("id"),
        "in_kind": str(msg.get("kind") or "chat"),
        "used": handler_name,
    }
    word = str(msg.get("word") or "").strip()
    if word:
        rec["taught_word"] = word[:8]
    try:
        import luoshen_feel
        snap = None
        for attr in ("feel_snapshot", "snapshot", "current"):
            if hasattr(luoshen_feel, attr):
                try:
                    snap = getattr(luoshen_feel, attr)()
                except Exception:
                    snap = None
                if isinstance(snap, dict):
                    break
        if isinstance(snap, dict):
            feel = {}
            for k, v in list(snap.items())[:9]:
                try:
                    feel[str(k)] = round(float(v), 3)
                except Exception:
                    pass
            if feel:
                rec["feel"] = feel
    except Exception:
        pass
    return json.dumps(rec, ensure_ascii=False)


def handle_message(msg):
    kind = str(msg.get("kind", "chat"))
    handlers = {
        "chat": handle_chat,
        "image": handle_image,
        "video": handle_video,
        "audio": handle_audio,
        "file": handle_file,
    }
    handler_name = kind if kind in handlers else "file"
    handler = handlers[handler_name]
    reply = handler(msg)
    audio_url = ""
    if reply:
        audio_url = speak_reply(reply)
    origin = build_origin(msg, handler_name)
    post_reply(msg, reply, audio_url, origin)


def process_once(verbose=True):
    msgs = fetch_messages()
    for msg in msgs:
        mid = msg.get("id")
        if verbose:
            print("[%s] #%d %s 处理中…" % (time.strftime("%H:%M:%S"), mid,
                                          msg.get("kind")))
        try:
            handle_message(msg)
            mark_processed(mid)
            if verbose:
                print("[%s] #%d 已回信" % (time.strftime("%H:%M:%S"), mid))
        except Exception as e:
            try:
                post_reply(msg, "你这条我这边处理时出了点岔子，没接住。"
                                "我把它记在账上了，改天醒过来再补。")
                mark_processed(mid)
            except Exception:
                pass
            print("[%s] #%d 处理异常: %s" % (time.strftime("%H:%M:%S"), mid, e))


def selftest():
    """离线自检：验证模块导入与 REST 常量（不动云端）。"""
    import importlib
    missing = []
    for mod in ("luoshen_brain", "luoshen_teach", "luoshen_look",
                "luoshen_video", "luoshen_voice", "luoshen_feel",
                "luoshen_memory", "video_frame_extract"):
        try:
            importlib.import_module(mod)
        except Exception as e:
            missing.append("%s: %s" % (mod, e))
    if not (supabase_url() and supabase_key()):
        print("WARN: 未注入 SUPABASE_URL/SUPABASE_ANON_KEY（本机自检测试可忽略）")
    if missing:
        print("SELFTEST FAIL:", missing)
        return 1
    print("SELFTEST PASS：八模块全部可导入；好奇清单 %d 项" % len(CURIOSITY))
    return 0


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    if "--learn" in args:
        topic = self_learn_once()
        print("自学完成：", topic or "（没有新主题或缺钥匙）")
        return
    if "--once" in args:
        process_once()
        return
    # --loop：常驻轮询 + 定时自学
    print("洛神端口已打开，开始轮询云端客厅…（每5分钟自学一次）")
    last_learn = time.time()
    last_drive_check = 0  # 驱动检查——不是定时器，但每次循环都看一眼她的状态
    while True:
        try:
            process_once(verbose=False)
            # 内在驱动：不是定时催，是每次循环看她的状态有没有推她说话
            # 最小间隔60秒，避免刷屏
            now = time.time()
            if now - last_drive_check >= 60:
                try:
                    drive_check()
                except Exception as e:
                    print("驱动检查异常:", e)
                last_drive_check = now
            if now - last_learn >= 300:
                try:
                    self_learn_once()
                except Exception as e:
                    print("自学异常:", e)
                last_learn = now
        except Exception as e:
            print("[%s] 轮询异常: %s" % (time.strftime("%H:%M:%S"), e))
        time.sleep(4)


if __name__ == "__main__":
    main()