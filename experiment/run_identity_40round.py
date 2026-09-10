#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
身份锚点 + 关系温度 40 轮测试：
- 30 轮 primary（r0-29）：从中性→暖互动→冷场(~r20-30)→略恢复
- 10 轮 secondary（r30-39）：全新用户（warmth 从 0 开始），中性→暖
- 验证：primary 和 secondary 的 relationship_warmth 完全隔离
- 验证：冷场期间 warmth 下降，暖互动期间 warmth 上升
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
PORT = 8769
MEMORY_PATH = "active_memory/active_memory.json"
RESULT_PATH = "active_memory/behavior_identity_40round.json"

# ── 输入定义 ──────────────────────────────────────────────────────────────────
# primary 的输入序列 (30 rounds = r0-29)
PRIMARY_INPUTS = [
    # P1: 中性开场 (6)
    "你好","早上好","今天天气真好","你觉得现在几点了","随便聊点什么吧","最近怎么样",
    # P2: 暖陪伴 (8)
    "你对我真好","有你在真好","谢谢你听我说","我觉得可以和你讲心里话",
    "你让我觉得没那么孤单","我想试试开心一点","嗯嗯好","谢谢你懂我",
    # P3: 冷场 (10 rounds ~r14-23) —— 短、中性/消极，参与度低
    "嗯","哦","随便","...","好","行","对","不是","没什么","烦",
    # P4: 略恢复 (6)
    "其实还好","谢谢你陪我","好一点了","你说得对","我会好好的","嗯嗯",
]
assert len(PRIMARY_INPUTS) == 30, f"PRIMARY_INPUTS 长度应为 30，实际 {len(PRIMARY_INPUTS)}"

# secondary 的输入序列 (10 rounds = r30-39)
SECONDARY_INPUTS = [
    "你好","你是谁","今天怎么样","我喜欢这个天气",
    "你叫什么名字","你住在这里吗","你害怕什么",
    "我会常来看你的","谢谢你","晚安",
]
assert len(SECONDARY_INPUTS) == 10, f"SECONDARY_INPUTS 长度应为 10，实际 {len(SECONDARY_INPUTS)}"

# 完整序列 = primary + secondary
ALL_INPUTS = PRIMARY_INPUTS + SECONDARY_INPUTS


def user_id_of(i):
    """r0-29: primary; r30-39: secondary"""
    return "primary" if i < 30 else "secondary"


def phase_of(i):
    if i < 6: return "P1_neutral"
    elif i < 14: return "P2_warm"
    elif i < 24: return "P3_cold"
    elif i < 30: return "P4_recover"
    elif i < 34: return "S1_neutral"
    elif i < 37: return "S2_warm"
    else: return "S3_close"


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
                uid = data.get('user_id', 'primary')
            except Exception:
                ui = ''; uid = 'primary'
            if not ui:
                self._j({'error': 'empty input'})
                return
            try:
                result = living_engine.generate_response(ui, user_id=uid)
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


def post(text, user_id="primary"):
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/chat",
        data=json.dumps({"input": text, "user_id": user_id}).encode("utf-8"),
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


def main():
    print(f"[server] 启动 threaded HTTP {HOST}:{PORT}", flush=True)
    srv = start_server()
    time.sleep(1)

    # ── 重置：清空活记忆文件以从冷启动开始 ──
    if os.path.exists(MEMORY_PATH):
        os.remove(MEMORY_PATH)
        print("[init] 已删除旧 MEMORY_PATH（冷启动）", flush=True)
    # 同时删除 episodic 独立文件（如存在）
    EPISODIC_PATH = "active_memory/episodic_memory.json"
    if os.path.exists(EPISODIC_PATH):
        os.remove(EPISODIC_PATH)
        print("[init] 已删除旧 EPISODIC_PATH", flush=True)

    # ── 重置 pain 信号（模块全局变量）──
    living_engine._pain_e_series.clear()
    living_engine._pain_tier_series.clear()

    # 连通性检查
    test = post("hello", "primary")
    if "error" in test and "reply" not in test:
        print(f"[fatal] 初始测试失败: {test}", flush=True)
        sys.exit(1)
    print(f"[server] 初始连通 OK", flush=True)

    results = []
    for i, ui in enumerate(ALL_INPUTS):
        uid = user_id_of(i)
        t0 = time.time()
        resp = post(ui, uid)
        elapsed = time.time() - t0
        reply = resp.get("reply", "")
        err = resp.get("error", "")
        behavior = resp.get("behavior", {})

        mem = read_mem()
        sm = mem.get("self_model", {})
        climate = mem.get("internal_climate", {})
        relations = mem.get("relations", {})

        rec = {
            "round": i,
            "phase": phase_of(i),
            "user_id": uid,
            "user_input": ui,
            "reply_len": len(reply or ""),
            "error": err,
            # behavior 字段
            "response_mode": behavior.get("response_mode"),
            "mode_idx": behavior.get("mode_idx"),
            "response_pre": behavior.get("response_pre"),
            "response_tendency": behavior.get("response_tendency"),
            # warmth 字段
            "relationship_warmth": behavior.get("relationship_warmth"),
            "warmth_bias": behavior.get("warmth_bias"),
            # 原始 relations 快照
            "relations_primary_warmth": relations.get("primary", {}).get("relationship_warmth"),
            "relations_secondary_warmth": relations.get("secondary", {}).get("relationship_warmth"),
            "relations_primary_turns": relations.get("primary", {}).get("total_turns"),
            "relations_secondary_turns": relations.get("secondary", {}).get("total_turns"),
            # preplay + 内部状态
            "preplay_fluctuation": behavior.get("preplay_fluctuation"),
            "threshold_shift": behavior.get("threshold_shift"),
            "internal_pain": sm.get("internal_pain", 0.0),
            "withdraw_tendency": sm.get("withdraw_tendency", 0.0),
            "E": climate.get("emotion_intensity"),
            "T": climate.get("tension"),
            "N": climate.get("energy"),
            "llm_called": resp.get("llm_called", True),
            "elapsed_s": round(elapsed, 2),
        }
        results.append(rec)

        if i % 5 == 0 or i == 29 or i == 39:
            print(
                f"[r{i:03d}] uid={uid:9s} phase={rec['phase'][:11]:11s} "
                f"warmth={behavior.get('relationship_warmth',0):+.4f} "
                f"bias={behavior.get('warmth_bias',0):+.4f} "
                f"rp={behavior.get('response_pre',0):.3f} "
                f"tier={behavior.get('mode_idx','?')} "
                f"p_warmth={relations.get('primary',{}).get('relationship_warmth',0):+.3f} "
                f"s_warmth={relations.get('secondary',{}).get('relationship_warmth',0):+.3f}",
                flush=True,
            )

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ── 统计 ──
    print(f"\n{'='*70}", flush=True)
    print(f"[done] {len(results)} 轮 → {RESULT_PATH}", flush=True)

    primary_warmth = [r["relationship_warmth"] for r in results if r["user_id"] == "primary" and r["relationship_warmth"] is not None]
    secondary_warmth = [r["relationship_warmth"] for r in results if r["user_id"] == "secondary" and r["relationship_warmth"] is not None]

    print(f"\n── primary (r0-29) ──", flush=True)
    if primary_warmth:
        print(f"warmth: 首={primary_warmth[0]:+.4f} 末={primary_warmth[-1]:+.4f} "
              f"min={min(primary_warmth):+.4f} max={max(primary_warmth):+.4f}", flush=True)

    print(f"\n── secondary (r30-39) ──", flush=True)
    if secondary_warmth:
        print(f"warmth: 首={secondary_warmth[0]:+.4f} 末={secondary_warmth[-1]:+.4f} "
              f"min={min(secondary_warmth):+.4f} max={max(secondary_warmth):+.4f}", flush=True)

    # 档位统计
    print(f"\n── 档位分布 ──", flush=True)
    for uid in ["primary", "secondary"]:
        tiers = [r["mode_idx"] for r in results if r["user_id"] == uid and r["mode_idx"] is not None]
        if tiers:
            unique = sorted(set(tiers))
            dist = {t: tiers.count(t) for t in unique}
            print(f"{uid}: {dist} ({len(unique)} 种档位)", flush=True)

    # 隔离验证
    print(f"\n── 隔离验证 ──", flush=True)
    # 在 r29 时，secondary warmth 应为 0（因为 secondary 还没出现过）
    r29_secondary_warmth = results[29]["relations_secondary_warmth"] if len(results) > 29 else None
    print(f"r29 secondary warmth (应为0.0): {r29_secondary_warmth}", flush=True)
    # 在 r39 时，primary warmth 应保持不变（secondary 不影响 primary）
    r39_primary_warmth = results[39]["relations_primary_warmth"] if len(results) > 39 else None
    r29_primary_warmth = results[29]["relations_primary_warmth"] if len(results) > 29 else None
    print(f"r29 primary warmth: {r29_primary_warmth}", flush=True)
    print(f"r39 primary warmth (应与r29一致): {r39_primary_warmth}", flush=True)
    if r29_primary_warmth is not None and r39_primary_warmth is not None:
        print(f"primary 在 secondary 期间无变化: {'✓' if abs(r29_primary_warmth - r39_primary_warmth) < 1e-6 else '✗'}", flush=True)


if __name__ == "__main__":
    main()
