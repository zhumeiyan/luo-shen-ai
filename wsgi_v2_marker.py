import sys, os, json, time, random

os.chdir("/home/zhumeiyan/luoshen")
os.environ.setdefault("ZHIPU_API_KEY", "3121fdd55f9340cba35f39fa2e312bc5.c4KrVxtLCPdCgARq")
sys.path.insert(0, "/home/zhumeiyan/luoshen")

# Ensure requests is available
try:
    import requests
except ImportError:
    import subprocess, glob
    home = os.path.expanduser("~")
    for sp in glob.glob(os.path.join(home, ".local", "lib", "python*", "site-packages")):
        if os.path.isdir(os.path.join(sp, "requests")):
            if sp not in sys.path:
                sys.path.insert(0, sp)
            break
    import requests

import living_engine, llm_interface

# Tick server paths
BASE_DIR = "/home/zhumeiyan/luoshen"
CHANNEL_PATH = os.path.join(BASE_DIR, "shared_context", "channel.jsonl")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
RAW_LOG_PATH = os.path.join(BASE_DIR, "auto_run_raw.jsonl")

TICK_SPEAKERS = ["luoshen", "executor"]


def tick_read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"turn": 0, "speaker": "luoshen", "max_turns": 10, "auto_run": True}


def tick_write_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def tick_read_last_n(n=5):
    if not os.path.exists(CHANNEL_PATH):
        return []
    with open(CHANNEL_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    msgs = []
    for l in lines:
        try:
            msgs.append(json.loads(l))
        except:
            pass
    return msgs[-n:]


def tick_build_prompt(messages, speaker):
    if not messages:
        return "你好。这是我们第一次对话。"
    parts = []
    for m in messages:
        who = m.get("who", "?")
        said = m.get("said", "")[:200]
        parts.append(f"[{who}] {said}")
    ctx = "\n\n".join(parts)
    if speaker == "luoshen":
        return f"以下是最近的多轮对话上下文：\n\n{ctx}\n\n请你基于上下文做简短回应（2-5句），继续推进话题。不要自我介绍，直接说你想说的话。"
    else:
        return f"以下是最近的多轮对话上下文：\n\n{ctx}\n\n请你以[执行端]身份做简短回应（2-5句）。要求：真实、不套话、有具体内容、回应前文。"


def tick_generate_executor(prompt):
    """Executor 自动生成回复 - 基于上下文的模板 + 随机"""
    lines = prompt.split("\n")
    last_luoshen_line = ""
    for l in reversed(lines):
        if "[luoshen]" in l.lower() or "luoshen" in l.lower():
            last_luoshen_line = l
            break

    templates = [
        "嗯。你说的我听到了。但我还有一个问题想问。",
        "是的。这是其中一面。另一面是——这件事也许没有看起来那么简单。",
        "我理解你的意思。但接不接受是另一回事。",
        "你说的有上下文。在这个上下文里，你的判断是对的。",
        "等一下。你刚才那句话让我想到一个别的方向。",
        "好。这件事我先接住。你往下的推导是什么？",
        "我不反驳你。但我想在这里停一下，看看这句话背后是什么。",
        "嗯。这里有一个东西你想过没有——你说的这个，和前面说的那个，是不是同一件事？",
        "你说的让我有点意外。继续说。",
        "我想确认一下：你说的这个，是在描述一个状态，还是在做一个判断？",
        "你说的有意义。但我注意到你跳过了中间的一步。",
        "对。但这意味着什么？"
    ]
    return random.choice(templates)


def tick_write_channel(who, said, reading_ts):
    msg = {"ts": time.time(), "who": who, "said": said, "reading": reading_ts}
    with open(CHANNEL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return msg


def tick_write_raw(round_num, speaker, prompt, reply):
    entry = {"round": round_num, "ts": time.time(), "speaker": speaker,
             "prompt_len": len(prompt), "reply_len": len(reply),
             "reply_preview": reply[:300]}
    with open(RAW_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def tick_do_tick():
    result = {"status": "error", "error": "unknown"}
    try:
        state = tick_read_state()
        turn = state.get("turn", 0)
        max_turns = state.get("max_turns", 10)

        if turn >= max_turns:
            return {"status": "finished", "turn": turn, "message": f"Already completed {turn}/{max_turns} rounds."}

        speaker = state.get("speaker", "luoshen")
        last_msgs = tick_read_last_n(5)
        prompt = tick_build_prompt(last_msgs, speaker)

        if speaker == "luoshen":
            try:
                reply = living_engine.process_user_input(prompt, user_id="auto_tick")
            except Exception as e:
                reply = f"[luoshen error: {str(e)[:100]}]"
            said = f"[洛神]\n\n{reply}"
        else:
            reply = tick_generate_executor(prompt)
            said = reply

        reading_ts = last_msgs[-1]["ts"] if last_msgs else None
        msg = tick_write_channel(speaker, said, reading_ts)
        tick_write_raw(turn, speaker, prompt, reply)

        next_speaker = "executor" if speaker == "luoshen" else "luoshen"
        new_turn = turn + 1 if next_speaker == "luoshen" else turn
        new_state = {"turn": new_turn, "speaker": next_speaker, "max_turns": max_turns,
                     "auto_run": state.get("auto_run", True),
                     "last_tick_ts": time.time(), "last_speaker": speaker, "last_msg_ts": msg["ts"]}
        tick_write_state(new_state)

        try:
            mem = living_engine._load_json("active_memory/active_memory.json")
            energy = mem.get("internal_climate", {}).get("energy", "?")
            tension = mem.get("internal_climate", {}).get("tension", "?")
            pain = mem.get("self_model", {}).get("internal_pain", "?")
            withdraw = mem.get("self_model", {}).get("withdraw_tendency", "?")
        except:
            energy = tension = pain = withdraw = "?"

        result = {"status": "ok", "round_executed": turn, "speaker": speaker,
                  "next_speaker": next_speaker, "next_turn": new_turn, "max_turns": max_turns,
                  "reply_preview": reply[:300], "energy": energy, "tension": tension,
                  "pain": pain, "withdraw": withdraw, "msg_ts": msg["ts"]}
    except Exception as e:
        import traceback
        result = {"status": "error", "error": str(e), "traceback": traceback.format_exc()[:1000]}
    return result


# ─── Original web chat handlers ───

HTML_INDEX = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>洛神</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:sans-serif;background:#f5f5f5;max-width:720px;margin:0 auto;padding:20px}
#c{background:#fff;border-radius:12px;padding:20px;min-height:200px;margin-bottom:16px}
.m{margin:10px 0;padding:10px 16px;border-radius:18px;max-width:85%;line-height:1.6;word-break:break-word}
.u{background:#95ec69;margin-left:auto}.l{background:#eee}.e{background:#ffebee;color:#c62828}
form{display:flex;gap:8px}input{flex:1;padding:12px;border:1px solid #ddd;border-radius:24px;font-size:15px}
button{padding:12px 24px;background:#95ec69;border:none;border-radius:24px;font-size:15px;cursor:pointer}
button:hover{background:#7ed957}</style></head><body>
<h2 style="text-align:center;margin:15px 0">洛神</h2>
<div id="c"><div class="m" style="background:#e3f2fd;text-align:center">输入文字，按回车发送</div></div>
<form id="f"><input id="i" placeholder="输入消息..."/><button type="submit">发送</button></form>
<script>
const c=document.getElementById("c"),f=document.getElementById("f"),inp=document.getElementById("i");
f.addEventListener("submit",async e=>{
  e.preventDefault();
  const t=inp.value.trim();
  if(!t)return;
  const d=document.createElement("div");d.className="m u";d.textContent=t;c.appendChild(d);
  c.scrollTop=c.scrollHeight;inp.value="";inp.disabled=true;
  try{
    const r=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({input:t,user_id:"zhumeiyan"})});
    const j=await r.json();
    const m=document.createElement("div");m.className=j.error?"m e":"m l";
    m.textContent=j.error?j.error:j.reply;c.appendChild(m);
  }catch(err){
    const m=document.createElement("div");m.className="m e";m.textContent="ERR: "+err.message;c.appendChild(m);
  }finally{inp.disabled=false;inp.focus();c.scrollTop=c.scrollHeight;}
});
</script></body></html>"""


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    if path == "/" and method == "GET":
        start_response("200 OK", [("Content-Type","text/html; charset=utf-8")])
        return [HTML_INDEX.encode("utf-8")]

    if path == "/health" and method == "GET":
        start_response("200 OK", [("Content-Type","application/json")])
        return [json.dumps({"ok":True,"service":"luoshen-ai","wsgi_version":"v2_tick"}).encode("utf-8")]

    if path in ("/tick", "/tick/"):
        is_get = method == "GET"
        if is_get or method == "POST":
            result = tick_do_tick()
            start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
            return [json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")]
        else:
            start_response("405 Method Not Allowed", [("Content-Type","text/plain")])
            return [b"POST or GET /tick"]

    if path == "/state" and method == "GET":
        state = tick_read_state()
        start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
        return [json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")]

    if path == "/chat" and method == "POST":
        try:
            cl = int(environ.get("CONTENT_LENGTH", 0))
            body = environ["wsgi.input"].read(cl)
            data = json.loads(body)
            user_input = data.get("input", "")
            user_id = data.get("user_id", "primary")
        except Exception:
            user_input=""; user_id="primary"

        if not user_input:
            start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
            return [json.dumps({"error":"输入为空"}, ensure_ascii=False).encode("utf-8")]

        try:
            reply = living_engine.process_user_input(user_input, user_id=user_id)
            start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
            return [json.dumps({"reply":reply,"user_id":user_id}, ensure_ascii=False).encode("utf-8")]
        except Exception as e:
            start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
            return [json.dumps({"error":"洛神暂时无法回复: "+str(e)}, ensure_ascii=False).encode("utf-8")]

    if path in ("/diag", "/diagnostic") and method == "GET":
        start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
        try:
            mem = living_engine._load_json("active_memory/active_memory.json")
            result = {
                "state": {
                    "energy": mem.get("internal_climate", {}).get("energy"),
                    "tension": mem.get("internal_climate", {}).get("tension"),
                    "withdraw_tendency": mem.get("self_model", {}).get("withdraw_tendency"),
                    "internal_pain": mem.get("self_model", {}).get("internal_pain"),
                }
            }
        except Exception as e:
            result = {"error": str(e)}
        return [json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")]

    start_response("404 Not Found", [("Content-Type","text/plain")])
    return [b"Not Found"]
