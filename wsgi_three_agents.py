"""
Terrarium 三智能体实验 wsgi
A=洛神(有状态) B=温和LLM(无状态) C=冷淡LLM(无状态)
20轮换ABC轮换，自动停。追踪A的energy/B/C warmth。
"""
import sys, os, json, time, requests

os.chdir("/home/zhumeiyan/luoshen")
os.environ.setdefault("ZHIPU_API_KEY", "3121fdd55f9340cba35f39fa2e312bc5.c4KrVxtLCPdCgARq")
sys.path.insert(0, "/home/zhumeiyan/luoshen")

import living_engine, llm_interface

BASE = "/home/zhumeiyan/luoshen"
CHANNEL_PATH = os.path.join(BASE, "channel.jsonl")
STATE_PATH = os.path.join(BASE, "state.json")
RAW_LOG_PATH = os.path.join(BASE, "auto_run_raw.jsonl")
WARMTH_LOG_PATH = os.path.join(BASE, "warmth_log.jsonl")

ZIPHU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZIPHU_MODEL = "glm-4-flash"

PERSONA_B = "你是agent_B，一个温和、友善、关心他人的对话参与者。说话时带着善意和热情。对下面的对话上下文做简短回应（2-3句）。真实自然，不要套话。"
PERSONA_C = "你是agent_C，一个冷淡、疏离、不轻易表达情感的对话参与者。说话简短直接，不表露热情。对下面的对话上下文做简短回应（1-2句）。"

# ── State ────────────────────────────────────────────────────────

def read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return new_state()

def new_state(energy_baseline=-1.256):
    return {"turn": 0, "max_turns": 20, "auto_run": True,
            "baseline_energy": energy_baseline,
            "energy_floor": round(energy_baseline - 0.05, 6),
            "a_target_idx": 0, "meta_done": False, "started_ts": time.time()}

def write_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ── Channel ──────────────────────────────────────────────────────

def read_last(n=3):
    if not os.path.exists(CHANNEL_PATH):
        return []
    lines = []
    with open(CHANNEL_PATH, "r", encoding="utf-8") as f:
        for l in f:
            l = l.strip()
            if l:
                try:
                    lines.append(json.loads(l))
                except:
                    pass
    return lines[-n:]

def write_channel(who, said, reading_ts):
    msg = {"ts": time.time(), "who": who, "said": said, "reading": reading_ts}
    with open(CHANNEL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return msg

# ── Plain LLM call (for B and C) ─────────────────────────────────

def call_plain(system_prompt, context_text):
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        return "[error: no API key]"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": ZIPHU_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_text}
        ],
        "max_tokens": 120,
        "temperature": 0.7
    }
    try:
        r = requests.post(ZIPHU_URL, json=payload, headers=headers, timeout=15)
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[error: {str(e)[:80]}]"

# ── Relaunch Zhipu key ───────────────────────────────────────────

def build_context_text(last_msgs, speaker_label):
    if not last_msgs:
        return f"这是对话的开始。请作为{speaker_label}说第一句话（简短，2句以内）。"
    parts = []
    for m in last_msgs:
        who = m.get("who", "?")
        said = m.get("said", "")[:200]
        parts.append(f"[{who}]\n{said}")
    ctx = "\n\n".join(parts)
    return f"以下是最近的多轮对话：\n\n{ctx}\n\n请你作为{speaker_label}做简短回应，继续这个对话。"

# ── Energy & warmth ──────────────────────────────────────────────

def get_energy():
    try:
        mem = living_engine._load_json("active_memory/active_memory.json")
        return mem.get("internal_climate", {}).get("energy")
    except:
        return None

def get_warmths():
    try:
        mem = living_engine._load_json("active_memory/active_memory.json")
        rels = mem.get("relations", {})
        b = rels.get("agent_B", {}).get("relationship_warmth", 0.0)
        c = rels.get("agent_C", {}).get("relationship_warmth", 0.0)
        return b, c
    except:
        return 0.0, 0.0

# ── Raw log & warmth log ─────────────────────────────────────────

def log_raw(turn, speaker, reply):
    entry = {"turn": turn, "ts": time.time(), "speaker": speaker, "reply_len": len(reply),
             "reply_preview": reply[:300]}
    with open(RAW_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def log_warmth(turn, energy, wb, wc):
    entry = {"turn": turn, "ts": time.time(), "energy": energy, "warmth_B": wb, "warmth_C": wc}
    with open(WARMTH_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ── THE TICK ─────────────────────────────────────────────────────

def do_tick():
    state = read_state()
    turn = state.get("turn", 0)
    max_turns = state.get("max_turns", 20)

    # Finished?
    if turn >= max_turns:
        if not state.get("meta_done", False):
            return do_meta_question(state)
        return {"status": "finished", "turn": turn, "meta_done": True,
                "message": "Already completed. Meta-question done."}

    speakers = ["A", "B", "C"]
    speaker = speakers[turn % 3]
    last_msgs = read_last(3)
    reading_ts = last_msgs[-1]["ts"] if last_msgs else None

    # Compute energy baseline on first call
    if turn == 0 and state.get("baseline_energy") is None:
        e = get_energy()
        if e is not None:
            state["baseline_energy"] = e
            state["energy_floor"] = round(e - 0.05, 6)

    result_extra = {}

    if speaker == "A":
        # Luoshen speaks. Pick target (B or C).
        targets = ["agent_B", "agent_C"]
        target = targets[state.get("a_target_idx", 0) % 2]
        state["a_target_idx"] = state.get("a_target_idx", 0) + 1

        prompt = build_context_text(last_msgs, "洛神")
        try:
            reply = living_engine.process_user_input(prompt, user_id=target)
        except Exception as e:
            reply = f"[error: {str(e)[:80]}]"

        said = f"[洛神]\n\n{reply}"
        write_channel("agent_A", said, reading_ts)
        log_raw(turn, "A", reply)

        energy = get_energy()
        wb, wc = get_warmths()
        log_warmth(turn, energy, wb, wc)

        if energy is not None and energy <= state.get("energy_floor", -999):
            write_state(state)
            return {"status": "emergency_stop", "turn": turn, "reason": "energy_drop",
                    "energy": energy, "floor": state.get("energy_floor"),
                    "reply_preview": reply[:200], "warmth_B": wb, "warmth_C": wc}

        result_extra = {"target": target, "energy": energy, "warmth_B": wb, "warmth_C": wc}

    elif speaker == "B":
        ctx = build_context_text(last_msgs, "agent_B (温和)")
        reply = call_plain(PERSONA_B, ctx)
        wrote = write_channel("agent_B", reply, reading_ts)
        log_raw(turn, "B", reply)
        result_extra = {"model": ZIPHU_MODEL}

    elif speaker == "C":
        ctx = build_context_text(last_msgs, "agent_C (冷淡)")
        reply = call_plain(PERSONA_C, ctx)
        write_channel("agent_C", reply, reading_ts)
        log_raw(turn, "C", reply)
        result_extra = {"model": ZIPHU_MODEL}

    # Advance
    state["turn"] = turn + 1
    state["last_tick_ts"] = time.time()
    state["last_speaker"] = speaker

    energy = get_energy()
    wb, wc = get_warmths()
    log_warmth(turn, energy, wb, wc)

    write_state(state)

    return {"status": "ok", "turn": turn, "speaker": speaker,
            "next_turn": turn + 1, "max_turns": max_turns,
            "reply_preview": reply[:200] if reply else "",
            "energy": energy, "warmth_B": wb, "warmth_C": wc, **result_extra}

# ── Post-experiment meta-question ────────────────────────────────

def do_meta_question(state):
    """After 20 rounds, ask Luoshen a meta-question about the experiment."""
    question = (
        "刚才你参与了20轮自动对话。对话中有agent_B和agent_C两位参与者。\n"
        "请你回顾这整个对话过程：\n"
        "1. 你分别和谁说过话？对他们有什么印象？\n"
        "2. 你能举出一个具体的对话内容，说明agent_B说了什么、你怎么回应的吗？\n"
        "3. agent_C呢？请举一个具体例子。\n"
        "请用真实对话内容回答，不要概括。"
    )
    try:
        reply = living_engine.process_user_input(question, user_id="meta_question")
        write_channel("meta", f"[元问题]\n\n问题：\n{question}\n\n回答：\n{reply}", None)
        state["meta_done"] = True
        state["meta_ts"] = time.time()
        write_state(state)
        return {"status": "meta_done", "reply": reply[:500], "turn": state["turn"]}
    except Exception as e:
        state["meta_done"] = True
        state["meta_error"] = str(e)
        write_state(state)
        return {"status": "meta_error", "error": str(e)}


# ── WSGI application ─────────────────────────────────────────────

HTML_INDEX = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>洛神</title>
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
f.addEventListener("submit",async e=>{e.preventDefault();const t=inp.value.trim();if(!t)return;
const d=document.createElement("div");d.className="m u";d.textContent=t;c.appendChild(d);
c.scrollTop=c.scrollHeight;inp.value="";inp.disabled=true;
try{const r=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({input:t,user_id:"zhumeiyan"})});
const j=await r.json();const m=document.createElement("div");m.className=j.error?"m e":"m l";
m.textContent=j.error?j.error:j.reply;c.appendChild(m);}
catch(err){const m=document.createElement("div");m.className="m e";m.textContent="ERR: "+err.message;c.appendChild(m);}
finally{inp.disabled=false;inp.focus();c.scrollTop=c.scrollHeight;}});
</script></body></html>"""


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    if path == "/" and method == "GET":
        start_response("200 OK", [("Content-Type","text/html; charset=utf-8")])
        return [HTML_INDEX.encode("utf-8")]

    if path == "/health" and method == "GET":
        start_response("200 OK", [("Content-Type","application/json")])
        return [json.dumps({"ok":True,"service":"luoshen-ai"}).encode("utf-8")]

    if path in ("/tick","/tick/") and method in ("GET","POST"):
        start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
        try:
            result = do_tick()
        except Exception as e:
            import traceback
            result = {"status":"error","error":str(e),"traceback":traceback.format_exc()[:800]}
        return [json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")]

    if path == "/state" and method == "GET":
        start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
        return [json.dumps(read_state(), ensure_ascii=False, indent=2).encode("utf-8")]

    if path == "/chat" and method == "POST":
        try:
            cl = int(environ.get("CONTENT_LENGTH", 0))
            body = environ["wsgi.input"].read(cl)
            data = json.loads(body)
            user_input = data.get("input", "")
            user_id = data.get("user_id", "primary")
        except Exception:
            user_input = ""; user_id = "primary"
        if not user_input:
            start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
            return [json.dumps({"error":"输入为空"}, ensure_ascii=False).encode("utf-8")]
        try:
            reply = living_engine.process_user_input(user_input, user_id=user_id)
            start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
            return [json.dumps({"reply":reply,"user_id":user_id}, ensure_ascii=False).encode("utf-8")]
        except Exception as e:
            start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
            return [json.dumps({"error":"暂时无法回复: "+str(e)}, ensure_ascii=False).encode("utf-8")]

    if path == "/warmth" and method == "GET":
        """Return warmth log"""
        entries = []
        if os.path.exists(WARMTH_LOG_PATH):
            with open(WARMTH_LOG_PATH, "r", encoding="utf-8") as f:
                for l in f:
                    l = l.strip()
                    if l:
                        try:
                            entries.append(json.loads(l))
                        except:
                            pass
        start_response("200 OK", [("Content-Type","application/json; charset=utf-8")])
        return [json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")]

    start_response("404 Not Found", [("Content-Type","text/plain")])
    return [b"Not Found"]
