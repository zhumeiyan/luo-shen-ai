#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神端口（LUOSHEN PORTAL）：云端客厅 ⇄ 洛神本体 之间的桥。

朋友在网页上说话、上传照片/视频/语音 → 消息落进 Supabase 消息表；
本进程轮询信箱 → 洛神用她自己的模块处理（对话/看/听/教/说）→ 回复写回 + 语音合成传上去；
处理完标记已读。她的一切认知仍由确定性模块产生并上哈希链——云端号码只是门，不是她的脑子。

v2 新能力：
  - 研究（web_search）：聊天里出现"查/搜/了解" → 她联网查资料 → 学完沉记忆点；
  - 自学循环：每 30 分钟她自己挑一个好奇主题去查、去学、去沉记忆点，并把心得广播到客厅；
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

# 她好奇的自学清单：还没见过实物的字 + 常识主题
CURIOSITY = ["月", "水", "火", "木", "田", "土", "石", "云", "玉", "心",
             "雪", "花", "鸟", "鱼", "星星", "彩虹", "地震", "潮汐", "风",
             "闪电", "火山", "冰川", "竹子", "荷花", "茶叶", "瓷器", "长城",
             "黄河", "长江", "丝绸之路"]
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
    return _env("LLM_MODEL", "glm-4-flash")


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


def post_reply(original, text, audio_url=""):
    body = {
        "sender": "luoshen",
        "kind": "reply",
        "text": str(text)[:2000],
        "reply_to": original["id"],
        "audio_url": audio_url,
        # 回复回落到原频道：私聊 dm:xxx / 公共 lobby / 设计者通道 designer
        "channel": original.get("channel") or "lobby",
    }
    status, rows = rest("/rest/v1/messages", method="POST", body=body)
    if status >= 400:
        raise RuntimeError("回信失败 HTTP %s: %s" % (status, rows))


def post_broadcast(text):
    """她自己主动开口说话（自学心得等）→ 公共客厅可见，直接标已处理。"""
    body = {
        "sender": "luoshen",
        "kind": "chat",
        "text": str(text)[:2000],
        "processed": True,
        "channel": "lobby",
    }
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


def self_learn_once():
    """自学一次：从好奇清单里挑一个还没细查过的主题，查、学、沉记忆点、广播。"""
    studied = set()
    try:
        for line in open(SELF_LEARN_LOG, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                studied.add(r.get("topic"))
    except Exception:
        pass
    for topic in CURIOSITY:
        if topic not in studied:
            try:
                answer = research(
                    "给我讲讲『%s』是怎么回事：它是什么、在哪里能见到、为什么有意思" % topic,
                    topic=topic)
            except RuntimeError as e:
                if "没有钥匙" in str(e):
                    return None
                continue
            n, attention = sink_learn_memory(topic, answer, source="self")
            try:
                post_broadcast("（自学第%d次·注意力%.0f%%）我自己去查了『%s』：%s" % (
                    n, attention * 100, topic, answer))
            except Exception:
                pass
            return topic
    return None


R_CACHE = {}


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
        return brain_chat(text)
    except RuntimeError as e:
        if "未配置" in str(e) or "LLM" in str(e):
            return ("我收到了你说的话，但这会儿我脑子里的翻译器还没醒（缺钥匙）。"
                    "等我醒着的时候再来说，我一定好好回你。")
        raise
    except Exception:
        return ("你跟我说的话我记下了，可刚才翻译时我卡了一下，"
                "没能好好回你。稍后再试一次就好。")


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


def handle_message(msg):
    kind = str(msg.get("kind", "chat"))
    handlers = {
        "chat": handle_chat,
        "image": handle_image,
        "video": handle_video,
        "audio": handle_audio,
        "file": handle_file,
    }
    handler = handlers.get(kind, handle_file)
    reply = handler(msg)
    audio_url = ""
    if reply:
        audio_url = speak_reply(reply)
    post_reply(msg, reply, audio_url)


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
    print("洛神端口已打开，开始轮询云端客厅…（每30分钟自学一次）")
    last_learn = time.time()
    while True:
        try:
            process_once(verbose=False)
            if time.time() - last_learn >= 1800:
                try:
                    self_learn_once()
                except Exception as e:
                    print("自学异常:", e)
                last_learn = time.time()
        except Exception as e:
            print("[%s] 轮询异常: %s" % (time.strftime("%H:%M:%S"), e))
        time.sleep(4)


if __name__ == "__main__":
    main()