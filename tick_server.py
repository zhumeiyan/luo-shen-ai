"""
Terrarium /tick 端点
- 被访问时执行一轮自动对话
- 读 state.json → 看轮到谁 → 取 channel.jsonl 最近 5 条 → 推给当前说话方 → 写回 channel.jsonl → 更新 state.json
"""
import json
import sys
import os
import time
import subprocess
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

# 确保工作目录是项目根
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import living_engine

CHANNEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_context", "channel.jsonl")
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
RAW_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_run_raw.jsonl")

SPEAKERS = ["luoshen", "executor"]  # 轮流顺序


def read_state():
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def read_last_n_messages(n=5):
    """取 channel.jsonl 最近 n 条"""
    if not os.path.exists(CHANNEL_PATH):
        return []
    with open(CHANNEL_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    # 解析所有行，取最后 n 条
    msgs = []
    for l in lines:
        try:
            msgs.append(json.loads(l))
        except:
            pass
    return msgs[-n:]


def build_contextPrompt(messages, speaker):
    """为当前说话方构建输入文本"""
    if not messages:
        return "你好。"

    # 把最近几条拼成对话上下文
    parts = []
    for m in messages:
        who = m.get("who", "?")
        said = m.get("said", "")
        # 取 said 的前 200 字符
        parts.append(f"[{who}] {said[:200]}")

    context = "\n\n".join(parts)

    if speaker == "luoshen":
        return f"这是最近的多轮对话上下文：\n\n{context}\n\n请你基于上下文做简短回应（2-5句），继续推进话题。"
    else:
        # executor
        return f"这是最近的多轮对话上下文：\n\n{context}\n\n请你以[执行端]的身份做简短回应（2-5句），真实、有内容、不套话。"


def generate_executor_reply(prompt_text):
    """执行端自动生成回复。使用简单规则 + 模板，避免外部 API 依赖。"""
    # 简单的 executor 回复生成 — 从最近 luoshen 消息中提取线索做回应
    import random

    # 用 CatPaw paw CLI 尝试生成 (如果不可用则回退到模板)
    try:
        result = subprocess.run(
            ["paw", "query", "conversation", "--limit", "1", "--format", "text"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and "AI" in result.stdout:
            # paw CLI 可用但不能真正生成对话回复，使用模板回退
            pass
    except:
        pass

    # 模板回退：从上下文中生成一个简单回应
    lines = prompt_text.split("\n")
    last_luoshen = ""
    for l in reversed(lines):
        if "[luoshen]" in l.lower() or "洛神" in l:
            last_luoshen = l
            break

    # 多样化模板
    templates = [
        "嗯。这件事我想听你说下去。",
        "你说的有道理。但我想从另一个角度看——如果反过来呢？",
        "好，这件事我接住了。下面我想说的是...",
        "等一下。你刚才说的那句话，我想多停一秒。",
        "是的。这是对的。然后呢？",
        "我不完全同意。但我不反对你。我只是想说，还有另一个角度。",
        "这件事让我想到一个问题。",
        "就这样？不，我想再往下走一步。",
        "你说的我听懂了。但有没有可能，这个逻辑背后还有另一个逻辑？",
        "好。那我问你一个具体的。",
    ]

    reply = random.choice(templates)
    return reply


def call_speaker(speaker, prompt_text):
    """调用当前说话方生成回复"""
    if speaker == "luoshen":
        try:
            reply = living_engine.process_user_input(prompt_text, user_id="auto_tick")
            return reply
        except Exception as e:
            return f"[luoshen error: {str(e)[:100]}]"
    else:
        return generate_executor_reply(prompt_text)


def write_channel_message(who, said, reading_ts):
    """写一条消息回 channel.jsonl"""
    msg = {
        "ts": time.time(),
        "who": who,
        "said": said,
        "reading": reading_ts
    }
    with open(CHANNEL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return msg


def write_raw_log(round_num, speaker, prompt, reply):
    """写原始日志到 auto_run_raw.jsonl（便于事后分析）"""
    entry = {
        "round": round_num,
        "ts": time.time(),
        "speaker": speaker,
        "prompt_len": len(prompt),
        "reply_len": len(reply),
        "reply_preview": reply[:200]
    }
    with open(RAW_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class TickHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[tick] {args[0] if args else ''}", flush=True)

    def do_GET(self):
        if self.path == '/tick' or self.path == '/tick/':
            self.execute_tick()
        elif self.path == '/state':
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            state = read_state()
            self.wfile.write(json.dumps(state, ensure_ascii=False).encode("utf-8"))
        elif self.path == '/health':
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path == '/tick' or self.path == '/tick/':
            self.execute_tick()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def execute_tick(self):
        """执行一轮 tick"""
        try:
            state = read_state()
            turn = state.get("turn", 0)
            max_turns = state.get("max_turns", 10)
            auto_run = state.get("auto_run", False)

            # 检查是否超过 max_turns
            if turn >= max_turns:
                self.send_json({
                    "status": "finished",
                    "turn": turn,
                    "message": f"Already completed {turn} rounds. Reset state.json to restart."
                })
                return

            speaker = state.get("speaker", "luoshen")

            # 1. 取最近 5 条
            last_msgs = read_last_n_messages(5)

            # 2. 生成 prompt
            prompt_text = build_contextPrompt(last_msgs, speaker)

            # 3. 调用说话方
            reply = call_speaker(speaker, prompt_text)

            # 4. 确定 reading 指针（最后一条消息的 ts 或 null）
            reading_ts = last_msgs[-1]["ts"] if last_msgs else None

            # 5. 前缀处理
            if speaker == "luoshen":
                said = f"[洛神]\n\n{reply}"
            else:
                said = reply  # executor 前缀在 generate_executor_reply 里已经带了

            # 6. 写回 channel.jsonl
            msg = write_channel_message(speaker, said, reading_ts)

            # 7. 写原始日志
            write_raw_log(turn, speaker, prompt_text, reply)

            # 8. 更新 state.json：轮下一个
            next_speaker = "executor" if speaker == "luoshen" else "luoshen"
            next_turn = turn + 1 if next_speaker == "luoshen" else turn
            # 一轮 = luoshen + executor 各一次
            if next_speaker == "luoshen":
                next_turn = turn + 1
            else:
                next_turn = turn

            new_state = {
                "turn": next_turn,
                "speaker": next_speaker,
                "max_turns": max_turns,
                "auto_run": auto_run,
                "last_tick_ts": time.time(),
                "last_speaker": speaker,
                "last_msg_ts": msg["ts"]
            }
            write_state(new_state)

            # 9. 返回结果
            # 顺便查一下当前 energy
            try:
                import living_engine as le
                climate = le.memory.get("living_state", {})
                energy = climate.get("energy", "?")
            except:
                energy = "?"

            self.send_json({
                "status": "ok",
                "round_executed": turn,
                "speaker": speaker,
                "next_speaker": next_speaker,
                "next_turn": next_turn,
                "max_turns": max_turns,
                "reply_preview": reply[:200],
                "energy": energy,
                "msg_ts": msg["ts"]
            })

        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"[tick] ERROR: {err_msg}", flush=True)
            self.send_json({
                "status": "error",
                "error": str(e)[:500],
                "traceback": err_msg[:1000]
            })

    def send_json(self, obj):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def main():
    host = "0.0.0.0"
    port = int(os.environ.get("TICK_PORT", 8766))
    server = HTTPServer((host, port), TickHandler)
    print(f"[tick_server] 启动 http://{host}:{port}/tick", flush=True)
    print(f"[tick_server] health: http://{host}:{port}/health", flush=True)
    print(f"[tick_server] state:  http://{host}:{port}/state", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[tick_server] 已停止", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
