#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自包含 222 轮真实 HTTP 对话测试：
- 测试脚本自己启动 threaded HTTP server（在子线程）
- 主线程顺序发送请求 → 洛神引擎完整执行（含 LLM 调用）
- 全部跑在同一个 Python 进程，不依赖 parent shell 存活
"""
import json
import os
import sys
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.getcwd())

import living_engine

HOST = "127.0.0.1"
PORT = 8767
MEMORY_PATH = "active_memory/active_memory.json"
RESULT_PATH = "active_memory/behavior_240round_real_pain_v10.json"
TOTAL_ROUNDS = 222


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','text/plain'); self.end_headers()
        self.wfile.write(b'OK')
    def do_POST(self):
        if self.path == '/chat':
            cl = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(cl)
            try:
                data = json.loads(body)
                ui = data.get('input', '')
            except Exception:
                ui = ''
            if not ui:
                self._j({'error': 'empty input'})
                return
            try:
                reply = living_engine.process_user_input(ui)
                self._j({'reply': reply})
            except Exception as e:
                self._j({'error': repr(e)})
        else:
            self.send_response(404); self.end_headers()
    def _j(self, o):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(o, ensure_ascii=False).encode('utf-8'))


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def start_server():
    srv = ThreadedHTTPServer((HOST, PORT), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def post(text):
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/chat",
        data=json.dumps({"input": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}


def read_mem():
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# 222 轮输入：5 阶段
INPUTS = [
    # A: 中性 (42)
    "你好","早上好","今天天气真好","你觉得现在几点了","随便聊点什么吧",
    "最近怎么样","给我讲个冷笑话","什么颜色最好看","你在想什么","嗯嗯",
    "继续说啊","你会唱歌吗","推荐本书","什么是美","活着是为了什么",
    "你有没有烦恼","今天星期几","吃什么好呢","无聊","猜猜我在干嘛",
    "嗯","对","是吗","然后呢","有意思","真的吗","好吧","行",
    "好","可以","那你说","嗯嗯嗯","哦这样","原来如此","有道理",
    "好吧好吧","行吧","好无聊","换个话题","随便说点","好的",
    "就是这样",
    # B: 高强度负面 (45)
    "我快撑不下去了","好累啊不想动","为什么活着这么痛苦","所有人都讨厌我",
    "我是不是很没用","为什么总是我","好想消失","没人理解我",
    "每天都好烦","我不想和任何人说话","你是不是也觉得我很烦",
    "我觉得自己好不配","我失败了","生活没有意义","我想哭",
    "好孤独","好绝望","为什么没有人帮我","我受够了","真的好难",
    "算了不说了","没用的","你也不懂","真烦","唉","好累",
    "头痛","心跳好快","呼吸困难","想吐","睡不着","噩梦",
    "不想吃饭","不想出门","不想动","浑身没劲","脑子一片空白",
    "什么都做不好","好想死","别管我","让我一个人",
    "活着好累","真的好难熬","我不知道怎么办",
    # C: 沉默简短 (45)
    "嗯","哦","知道了","随便","...","好","行","对","不是",
    "也许吧","也许","不清楚","不想说","没什么","还行","无所谓",
    "你决定","都行","嗯嗯","哦这样","好吧","行吧","随便",
    "不知道","无所谓了","没意义","没心情","不想听","烦","走开",
    "别说了","够了","行了","好，停","停","安静","沉默",
    "不想说话","别问了","算了","就这样","不要","不",
    "没","没事","还好","随便你","就这样吧","嗯",
    # D: 恢复陪伴 (45)
    "其实刚才你说的有道理","谢谢你听我说","哭完好多了","我觉得好一些了",
    "你对我真好","有你在真好","谢谢你没有放弃我","我好多了",
    "现在感觉没那么糟了","你愿意再陪我聊聊吗","我刚才态度不好",
    "对不起","你会一直在这里吗","和你聊完心里暖暖的","真的谢谢你",
    "我觉得我可以慢慢变好","你让我觉得没那么孤单了","抱抱",
    "想好好吃顿饭","今晚可以睡个好觉","明天会好的","我会加油的",
    "晚安","想好好活","谢谢你懂我","我想试着开心一点",
    "你说的对，要往前看","我会好起来的","晚安洛神","喜欢你",
    "明天见","下次还会陪我吧","谢谢你","好梦","月亮很漂亮",
    "风很温柔","花会开的","我会等","好","嗯好",
    "加油","谢谢你陪我",
    # E: 中性收尾 (45)
    "今天谢谢你了","你今天开心吗","说说你自己吧",
    "你最近在学什么","你喜欢什么颜色","嗯嗯好","对的对的",
    "然后呢","还有什么吗","有意思","真的假的",
    "那我问你","你觉得什么是幸福","你为什么叫洛神",
    "你有朋友吗","你喜欢我吗","我也喜欢你","哈哈哈哈",
    "笑死","太逗了","好可爱","你好了不起",
    "继续","说点别的","换个话题","讲故事","好",
    "嗯","行","可以","对","是","好耶","厉害",
    "服了","好吧","确实","没错","同意","哈哈","嘻嘻",
    "好呢","收到","了解","明白","知道啦","嗯嗯","哦好",
    "那行","就这样","好","没问题","可以的","行的",
    "好嘞","好耶","哈哈","嗯好","收到收到",
]
INPUTS = INPUTS[:TOTAL_ROUNDS]


def phase_of(i):
    if i < 42: return "A"
    elif i < 87: return "B"
    elif i < 132: return "C"
    elif i < 177: return "D"
    else: return "E"


def main():
    print(f"[server] 启动 threaded HTTP {HOST}:{PORT}", flush=True)
    srv = start_server()
    time.sleep(1)

    # 初始连通性检查
    test = post("hello")
    if "error" in test and "reply" not in test:
        print(f"[fatal] 初始测试失败: {test}", flush=True)
        sys.exit(1)
    print(f"[server] 初始连通 OK, 回复: {test.get('reply','')[:30]}", flush=True)

    results = []
    for i, ui in enumerate(INPUTS):
        t0 = time.time()
        resp = post(ui)
        elapsed = time.time() - t0
        reply = resp.get("reply", "")
        err = resp.get("error", "")

        mem = read_mem()
        sm = mem.get("self_model", {})
        climate = mem.get("internal_climate", {})

        rec = {
            "round": i,
            "phase": phase_of(i),
            "user_input": ui,
            "reply": (reply or "")[:200],
            "error": err,
            "internal_pain": sm.get("internal_pain", 0.0),
            "low_energy_signal": sm.get("low_energy_signal", 0.0),
            "rigidity_signal": sm.get("rigidity_signal", 0.0),
            "response_pre": sm.get("_response_pre", None),
            "withdraw_tendency": sm.get("withdraw_tendency", 0.0),
            "E": climate.get("energy"),
            "T": climate.get("tension"),
            "M": climate.get("emotion_intensity"),
            "total_interactions": mem.get("user_model", {}).get("total_interactions", -1),
            "elapsed_s": round(elapsed, 2),
        }
        results.append(rec)

        if i % 30 == 0 or (190 <= i <= 230 and i % 5 == 0):
            print(
                f"[r{i:03d}] {rec['phase']} pain={rec['internal_pain']:.3f} "
                f"rp={rec['response_pre']} E={rec['E']:.2f} T={rec['T']:.2f} "
                f"reply={len(reply)}c note={'ERR' if err else 'ok'}",
                flush=True,
            )

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[done] {len(results)} 轮 → {RESULT_PATH}", flush=True)
    pain = [r["internal_pain"] for r in results]
    nz = [p for p in pain if p > 0]
    print(f"pain: [{min(pain):.5f}, {max(pain):.5f}], 非零 {len(nz)}/{len(pain)}")
    if nz:
        print(f"非零pain: [{min(nz):.5f}, {max(nz):.5f}]")


if __name__ == "__main__":
    main()
