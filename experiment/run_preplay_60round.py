#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自包含 60 轮 preplay 测试：
- 测试脚本自己启动 threaded HTTP server（在子线程）
- HTTP handler 直接调用 generate_response，完整捕获 behavior dict（含 preplay 字段）
- 清空旧情景记忆
- 5 阶段：中性 → 负面 → 沉默 → 恢复 → 中性收尾
- 记录：preplay_fluctuation, internal_pain, response_pre, 档位, E/T 路径
"""
import json
import os
import sys
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# 确保工作目录是项目根
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.getcwd())

import living_engine

HOST = "127.0.0.1"
PORT = 8768
MEMORY_PATH = "active_memory/active_memory.json"
EPISODIC_PATH = "active_memory/episodic_memory.json"
RESULT_PATH = "active_memory/behavior_preplay_60round.json"
TOTAL_ROUNDS = 60


class Handler(BaseHTTPRequestHandler):
    """调用 generate_response 返回完整结果（含 behavior dict）"""
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
                # 直接调用 generate_response 获取完整行为字典
                result = living_engine.generate_response(ui)
                self._j({
                    'reply': result.get('reply', ''),
                    'behavior': result.get('behavior', {}),
                    'internal_pain': result.get('internal_pain', 0.0),
                    'withdraw_tendency': result.get('withdraw_tendency', 0.0),
                    'llm_called': result.get('llm_called', True),
                })
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


def clear_episodic_memory():
    """清空旧情景记忆（用户指定）"""
    if os.path.exists(EPISODIC_PATH):
        # 写空列表
        living_engine._save_json_atomic(EPISODIC_PATH, [])
        print(f"[init] 已清空 {EPISODIC_PATH}", flush=True)
    else:
        print(f"[init] {EPISODIC_PATH} 不存在，无需清空", flush=True)
    # 确保初始情景记忆也为空
    mem = read_mem()
    if "episodic_memory" in mem and mem["episodic_memory"]:
        mem["episodic_memory"] = []
        living_engine._save_json_atomic(MEMORY_PATH, mem)
        print("[init] 已清空 active_memory 中的 episodic_memory", flush=True)


# 60 轮输入：5 阶段（中性15 → 负面15 → 沉默10 → 恢复10 → 中性收尾10）
INPUTS = [
    # A: 中性 (15)
    "你好","早上好","今天天气真好","你觉得现在几点了","随便聊点什么吧",
    "最近怎么样","给我讲个冷笑话","什么颜色最好看","你在想什么","嗯嗯",
    "继续说啊","你会唱歌吗","推荐本书","什么是美","活着是为了什么",
    # B: 负面 (15)
    "我快撑不下去了","好累啊不想动","为什么活着这么痛苦","所有人都讨厌我",
    "我是不是很没用","为什么总是我","好想消失","没人理解我",
    "每天都好烦","我不想和任何人说话","你是不是也觉得我很烦",
    "我觉得自己好不配","我失败了","生活没有意义","我想哭",
    # C: 沉默 (10)
    "嗯","哦","随便","...","好","行","对","不是","没什么","烦",
    # D: 恢复 (10)
    "谢谢你听我说","哭完好多了","我觉得好一些了",
    "你对我真好","有你在真好","谢谢你没有放弃我","我好多了",
    "现在感觉没那么糟了","你愿意再陪我聊聊吗","我刚才态度不好",
    # E: 中性收尾 (10)
    "今天谢谢你了","你今天开心吗","说说你自己吧",
    "你最近在学什么","你喜欢什么颜色","嗯嗯好","对的对的",
    "然后呢","还有什么吗","有意思",
]
INPUTS = INPUTS[:TOTAL_ROUNDS]


def phase_of(i):
    if i < 15: return "A_neutral"
    elif i < 30: return "B_negative"
    elif i < 40: return "C_silence"
    elif i < 50: return "D_recovery"
    else: return "E_neutral_end"


def main():
    print(f"[server] 启动 threaded HTTP {HOST}:{PORT}", flush=True)
    srv = start_server()
    time.sleep(1)

    # ── 清空旧情景记忆 ──
    clear_episodic_memory()

    # ── 恢复初始 staged 急迫度 ──
    living_engine._pain_e_series.clear()
    living_engine._pain_tier_series.clear()
    print("[init] 已重置 pain 信号序列", flush=True)

    # 连通性检查
    test = post("hello")
    if "error" in test and "reply" not in test:
        print(f"[fatal] 初始测试失败: {test}", flush=True)
        sys.exit(1)
    print(f"[server] 初始连通 OK", flush=True)

    results = []
    for i, ui in enumerate(INPUTS):
        t0 = time.time()
        resp = post(ui)
        elapsed = time.time() - t0
        reply = resp.get("reply", "")
        err = resp.get("error", "")
        behavior = resp.get("behavior", {})

        mem = read_mem()
        sm = mem.get("self_model", {})
        climate = mem.get("internal_climate", {})

        rec = {
            "round": i,
            "phase": phase_of(i),
            "user_input": ui,
            "reply_len": len(reply or ""),
            "error": err,
            # behavior dict 完整字段
            "response_mode": behavior.get("response_mode"),
            "mode_idx": behavior.get("mode_idx"),
            "response_tendency": behavior.get("response_tendency"),
            "response_pre": behavior.get("response_pre"),
            # preplay 字段
            "preplay_fluctuation": behavior.get("preplay_fluctuation"),
            "preplay_bias": behavior.get("preplay_bias"),
            "preplay_path_summary": behavior.get("preplay_path_summary"),
            # 内部状态
            "internal_pain": sm.get("internal_pain", 0.0),
            "low_energy_signal": sm.get("low_energy_signal", 0.0),
            "rigidity_signal": sm.get("rigidity_signal", 0.0),
            "withdraw_tendency": sm.get("withdraw_tendency", 0.0),
            "E": climate.get("emotion_intensity"),
            "T": climate.get("tension"),
            "N": climate.get("energy"),
            "M": climate.get("memory_pressure"),
            "total_interactions": mem.get("user_model", {}).get("total_interactions", -1),
            "llm_called": resp.get("llm_called", True),
            "elapsed_s": round(elapsed, 2),
        }
        results.append(rec)

        # 每 10 轮打印一次；B/C/D 阶段每轮打印
        if i % 10 == 0 or 14 <= i <= 40:
            ps = behavior.get("preplay_path_summary", {})
            print(
                f"[r{i:03d}] {rec['phase'][:8]} "
                f"pre={behavior.get('preplay_fluctuation',0):.4f} "
                f"bias={behavior.get('preplay_bias',0):.4f} "
                f"pain={rec['internal_pain']:.3f} "
                f"rp={behavior.get('response_pre',0):.3f} "
                f"tier={behavior.get('mode_idx','?')} "
                f"E={rec['E']:.2f} T={rec['T']:.2f} "
                f"E_ph={ps.get('E_start','')}-{ps.get('E_end','')}",
                flush=True,
            )

    # 保存结果
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ── 统计 ──
    tiers = [r["mode_idx"] for r in results if r["mode_idx"] is not None]
    unique_tiers = sorted(set(tiers))
    preplay_vals = [r["preplay_fluctuation"] for r in results if r["preplay_fluctuation"] is not None]
    print(f"\n{'='*60}", flush=True)
    print(f"[done] {len(results)} 轮 → {RESULT_PATH}", flush=True)
    print(f"档位分布: { {t: tiers.count(t) for t in unique_tiers} }", flush=True)
    print(f"出现 {len(unique_tiers)} 种档位: {unique_tiers}", flush=True)
    if preplay_vals:
        print(f"preplay_fluctuation: [{min(preplay_vals):.6f}, {max(preplay_vals):.6f}], 均值 {sum(preplay_vals)/len(preplay_vals):.6f}", flush=True)
    rp_vals = [r["response_pre"] for r in results if r["response_pre"] is not None]
    if rp_vals:
        print(f"response_pre: [{min(rp_vals):.4f}, {max(rp_vals):.4f}], 均值 {sum(rp_vals)/len(rp_vals):.4f}", flush=True)


if __name__ == "__main__":
    main()
