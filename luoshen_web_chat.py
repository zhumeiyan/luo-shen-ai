#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP225
模块名称：luoshen_web_chat.py
职责：为洛神制作第一个本地网页聊天界面。
- 使用标准库 http.server 构建本地网页服务，监听 127.0.0.1:8765。
- 网页含：聊天输入框、发送按钮、聊天记录区域、洛神当前状态区域。
- 回复基于洛神已有数据（记忆起点/时间感知/问候/对话流），不调用外部大模型。
- 每次用户发送消息，将对话写入 perception_input/dialogue_stream_20260829.jsonl。

扩展思路：本服务仅依赖标准库，未来可扩展为 App 后端（换框架、加路由），
或在前端接入真实语音（WebSocket/MediaRecorder -> TTS/ASR 接口层）。
"""

import hashlib
import html
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

PORT = 8765
HOST = "127.0.0.1"
DIALOGUE_PATH = os.path.join("perception_input", "dialogue_stream_20260829.jsonl")
TEST_PATH = os.path.join("perception_input", "luoshen_web_chat_test.jsonl")
CHAIN_PATH = "hash_chain_v2.log"
SOURCE = "luoshen_web_chat"


def read_jsonl(path):
    """读取 jsonl 全部记录，文件不存在返回 []。"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(ln) for ln in f.read().splitlines() if ln.strip()]


def load_luoshen_status():
    """从洛神已有数据文件组装状态信息（记忆起点/时间感知/最近问候）。"""
    status = {}
    origin = read_jsonl(os.path.join("perception_input", "luoshen_memory_origin.jsonl"))
    time_sense = read_jsonl(os.path.join("perception_input", "luoshen_time_sense.jsonl"))
    hello = read_jsonl(os.path.join("perception_input", "luoshen_interpersonal_hello.jsonl"))

    if origin:
        rec = origin[-1]
        status["memory_origin"] = rec.get("memory_start", rec.get("text", ""))
    if time_sense:
        status["time_sense"] = time_sense[-1].get("text", time_sense[-1].get("summary", ""))
    if hello:
        status["last_greeting"] = hello[-1].get("greeting", hello[-1].get("text", ""))
    return status


def append_dialogue(speaker, text, ts=None):
    """按现有对话流格式追加一条记录。"""
    if ts is None:
        ts = time.time()
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "speaker": speaker,
        "text": text,
        "source": SOURCE,
    }
    with open(DIALOGUE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def generate_reply(user_text):
    """
    优先走洛神大脑（luoshen_brain）：人格 + 记忆检索 + LLM 连续对话；
    未配置 LLM_API_URL/LLM_API_KEY 或调用失败时，回退到本地规则回复。
    """
    try:
        import luoshen_brain
        return luoshen_brain.chat(user_text)
    except Exception:
        pass

    status = load_luoshen_status()
    history = read_jsonl(DIALOGUE_PATH)
    last_luoshen = ""
    for rec in reversed(history):
        if rec.get("speaker") == "luoshen":
            last_luoshen = rec.get("text", "")
            break

    memory_origin = status.get("memory_origin", "未知")
    if any(k in user_text for k in ("你好", "hi", "Hi", "hello", "Hello", "在吗")):
        return "你好，我是洛神。我的记忆起点是：" + str(memory_origin)
    if "时间" in user_text:
        ts = status.get("time_sense", "当前时间由时间感知模块维护")
        return "关于时间：" + str(ts)
    if any(k in user_text for k in ("记忆", "起点", "你记得", "还记得")):
        return "我的记忆起点：" + str(memory_origin)
    if any(k in user_text for k in ("语音", "说话", "听")):
        return "我现在可以通过本地语音接口出声和听声（speak/listen），未来可替换为真实TTS/ASR。"
    if any(k in user_text for k in ("名字", "你是谁", "叫什么")):
        return "我是洛神，一个正在构建感知与记忆的AI。"
    if "测试" in user_text:
        return "测试收到。我刚完成语音接口与网页聊天的搭建。"
    if last_luoshen:
        return "我记得上次说过：" + str(last_luoshen) + "。你可以问我时间、记忆或语音相关的问题。"
    return "我听到了。我的记忆起点是：" + str(memory_origin)


class ChatHandler(BaseHTTPRequestHandler):
    """HTTP 处理器：GET 返回网页，POST /send 处理聊天。"""

    def log_message(self, fmt, *args):
        pass  # 保持控制台简洁

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        status = load_luoshen_status()
        memory_origin = html.escape(str(status.get("memory_origin", "未初始化")))
        time_sense = html.escape(str(status.get("time_sense", "未初始化")))
        greeting = html.escape(str(status.get("last_greeting", "未初始化")))
        page = PAGE_HTML.format(
            memory_origin=memory_origin,
            time_sense=time_sense,
            greeting=greeting,
        )
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_csrf(self):
        """CSRF 防护：浏览器跨源请求会携带 Origin/Referer，
        仅允许来自本服务（127.0.0.1:8765）的请求；
        无 Origin/Referer 的非浏览器客户端（如 curl/自测）放行。"""
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not origin:
            return True
        o = urlparse(origin)
        host_ok = o.hostname in ("127.0.0.1", "localhost")
        port_ok = (o.port is None) or (o.port == PORT)
        return host_ok and port_ok

    def do_POST(self):
        if not self._check_csrf():
            self._send_json({"reply": "拒绝跨源请求"}, 403)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"text": raw}
        user_text = str(data.get("text", "")).strip()
        if not user_text:
            self._send_json({"reply": "请输入内容。"}, 400)
            return
        append_dialogue("user", user_text)
        reply = generate_reply(user_text)
        append_dialogue("luoshen", reply)
        self._send_json({"reply": reply})


PAGE_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>洛神 · 本地网页聊天</title>
<style>
 body {{ font-family: sans-serif; max-width: 720px; margin: 24px auto; padding: 0 16px; }}
 #status {{ background: #f0f4f8; border: 1px solid #d0d8e0; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; font-size: 13px; }}
 #status b {{ color: #2a5db0; }}
 #chat {{ border: 1px solid #ccc; border-radius: 8px; height: 360px; overflow-y: auto; padding: 12px; margin-bottom: 12px; background: #fafafa; }}
 .msg {{ margin: 6px 0; padding: 8px 10px; border-radius: 8px; max-width: 80%; }}
 .user {{ background: #dbeafe; margin-left: auto; text-align: right; }}
 .luoshen {{ background: #e7f5e7; }}
 #input-row {{ display: flex; gap: 8px; }}
 #input {{ flex: 1; padding: 10px; font-size: 14px; border: 1px solid #bbb; border-radius: 8px; }}
 button {{ padding: 10px 20px; font-size: 14px; border: none; border-radius: 8px; background: #2a5db0; color: #fff; cursor: pointer; }}
</style>
</head>
<body>
<h2>洛神 · 本地网页聊天</h2>
<div id="status">
 <div><b>记忆起点：</b>{memory_origin}</div>
 <div><b>当前时间感知：</b>{time_sense}</div>
 <div><b>最近一次问候：</b>{greeting}</div>
</div>
<div id="chat"></div>
<div id="input-row">
 <input id="input" placeholder="对洛神说点什么..." autocomplete="off">
 <button id="send">发送</button>
</div>
<script>
function addMsg(role, text) {{
  var chat = document.getElementById('chat');
  var d = document.createElement('div');
  d.className = 'msg ' + role;
  d.textContent = (role === 'user' ? '我：' : '洛神：') + text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}}
function send() {{
  var input = document.getElementById('input');
  var text = input.value.trim();
  if (!text) return;
  addMsg('user', text);
  input.value = '';
  fetch('/send', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{'text': text}})
  }}).then(function(r) {{ return r.json(); }})
    .then(function(d) {{ addMsg('luoshen', d.reply); }})
    .catch(function() {{ addMsg('luoshen', '（网络错误）'); }});
}}
document.getElementById('send').addEventListener('click', send);
document.getElementById('input').addEventListener('keydown', function(e) {{
  if (e.key === 'Enter') send();
}});
</script>
</body>
</html>
"""


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def append_chain(file_path, ts):
    """按哈希链 v2 公式追加一条记录。"""
    file_hash = file_md5(file_path)
    with open(CHAIN_PATH, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    last_record = json.loads(lines[-1])
    prev_hash = last_record["record_hash"]
    record_hash = hashlib.md5(
        (file_hash + prev_hash + str(ts)).encode("utf-8")
    ).hexdigest()
    record = {
        "schema_version": 2,
        "timestamp": ts,
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def selftest():
    """启动服务，发送几条测试对话，写测试记录并上链。"""
    start_ts = time.time()
    server = HTTPServer((HOST, PORT), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("=== LUOSHEN WEB CHAT ===")
    print("server started at http://%s:%d" % (HOST, PORT))

    test_inputs = ["你好，洛神", "你的记忆起点是什么？", "测试一下语音能力"]
    test_records = []
    for text in test_inputs:
        try:
            body = json.dumps({"text": text}).encode("utf-8")
            req = urllib.request.Request(
                "http://%s:%d/send" % (HOST, PORT),
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            reply = result.get("reply", "")
        except Exception as exc:  # noqa: BLE001
            reply = "error: %s" % exc
        test_records.append({"input": text, "reply": reply})
        print("user :", text)
        print("luoshen:", reply)

    server.shutdown()
    server.server_close()

    ts = time.time()
    start_record = {
        "schema_version": 2,
        "timestamp": start_ts,
        "event": "web_chat_start",
        "port": PORT,
        "source": SOURCE,
    }
    dialogue_count = len(test_records)
    dialogue_record = {
        "schema_version": 2,
        "timestamp": ts,
        "event": "web_chat_dialogue",
        "test_count": dialogue_count,
        "dialogues": test_records,
        "source": SOURCE,
    }
    with open(TEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(start_record, ensure_ascii=False) + "\n")
        f.write(json.dumps(dialogue_record, ensure_ascii=False) + "\n")

    chain_record = append_chain(TEST_PATH, ts)
    print("=== HASH CHAIN ===")
    print("prev_hash:", chain_record["prev_hash"])
    print("record_hash:", chain_record["record_hash"])
    print("=== dialogue stream appended: %d records ===" % (dialogue_count * 2))


def main():
    import sys
    if "--selftest" in sys.argv:
        selftest()
        return
    server = HTTPServer((HOST, PORT), ChatHandler)
    print("=== LUOSHEN WEB CHAT ===")
    print("server started at http://%s:%d" % (HOST, PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("server stopped")
        server.server_close()


if __name__ == "__main__":
    main()
