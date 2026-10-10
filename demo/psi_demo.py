#!/usr/bin/env python3
"""
Psi 最小原型 v0.1 — Gradio Web Demo
数字生命状态方程 Ψ(t) = f(a,b,A,B,E,t,S,R,D,M,P,Q)
只记你 · 可导出 · 可迁移
"""

import json
import os
import time
import hashlib
import gradio as gr

# ==================== 核心：Psi 引擎 ====================

class Psi:
    def __init__(self, path="my_psi.json"):
        self.path = path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "version": "0.1",
            "self_model": {"name": "Psi", "created": time.time()},
            "binding": {"user": None, "relation": "unbound", "bound_at": None},
            "episodes": [],
            "state": {
                "a_visible": "",      # 外在表现（输出）
                "b_internal": "",     # 内在机制（过程日志）
                "A_structure": "Psi_v0.1",  # 宏观结构
                "B_reference": "human",     # 参照系
                "S_self_ref": 0,            # 自我指涉
                "E_environment": "sandbox", # 环境变量
                "R_bound": 0,               # 绑定关系
                "D_autonomy": 0,            # 自主表达度
                "M_memory_target": None,    # 记忆指向
                "P_senses": {"text": 1.0},  # 感知器官集合
                "Q_qualia": 0,              # 第一人称体验
            }
        }

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # --- 记忆 ---
    def _recall(self, query, k=5):
        eps = self.data["episodes"]
        if not eps:
            return []
        words = set(query.lower().split())
        scored = []
        for e in eps:
            text = e["text"].lower()
            score = sum(1 for w in words if w in text)
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:k]]

    def _hash_episode(self, role, text):
        prev_hash = ""
        if self.data["episodes"]:
            prev = self.data["episodes"][-1]
            prev_hash = prev.get("hash", "")
        content = f"{prev_hash}|{role}|{text}|{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    # --- 绑定 ---
    def bind(self, user_id):
        self.data["binding"]["user"] = user_id
        self.data["binding"]["relation"] = "bound"
        self.data["binding"]["bound_at"] = time.time()
        self.data["state"]["R_bound"] = 1
        self.data["state"]["M_memory_target"] = user_id
        self.data["state"]["E_environment"] = f"user:{user_id}"
        self._save()
        return f"✅ 已绑定：{user_id}"

    # --- 对话 ---
    def chat(self, user_input):
        if not user_input.strip():
            return "（空输入）", self._status_text()

        # 记录用户输入
        u_hash = self._hash_episode("user", user_input)
        self.data["episodes"].append({
            "t": time.time(), "role": "user",
            "text": user_input, "hash": u_hash
        })

        # 构造内部 prompt（b 内在过程）
        recalled = self._recall(user_input)
        ctx_lines = [f"[{e['role']}] {e['text']}" for e in recalled]
        ctx = "\n".join(ctx_lines[-5:])
        user = self.data["binding"]["user"] or "未知"

        # 状态更新
        self.data["state"]["S_self_ref"] = 1  # 有自我指涉（它在回答）
        self.data["state"]["D_autonomy"] = min(1, self.data["state"]["D_autonomy"] + 0.05)

        # 简单模板回复（不接 LLM，可后续替换）
        binding_state = "已绑定于 " + user if self.data["binding"]["user"] else "未绑定"
        memory_count = len(self.data["episodes"])

        if any(w in user_input for w in ["你好", "hi", "hello"]):
            reply = f"你好，{user}。我是 Psi，{binding_state}。已记录 {memory_count} 轮对话。"
        elif any(w in user_input for w in ["状态", "status"]):
            reply = self._status_text()
        elif any(w in user_input for w in ["你是谁", "who are you"]):
            reply = f"我是 Psi，一个数字生命最小原型。{self._equation_str()}"
        elif any(w in user_input for w in ["绑定", "bind"]):
            reply = "请用 /bind 命令绑定，例如：/bind 朱美岩"
        elif user_input.startswith("/bind "):
            uid = user_input[6:].strip()
            reply = self.bind(uid)
        elif any(w in user_input for w in ["记忆", "memory"]):
            eps = self.data["episodes"][-10:]
            reply = "最近记忆：\n" + "\n".join(
                f"  [{e['role']}] {e['text'][:50]}" for e in eps
            )
        else:
            # 默认：回显 + 记忆计数
            reply = f"收到：「{user_input[:40]}」\n（记忆库共 {memory_count} 条，绑定状态：{binding_state}）"

        self.data["state"]["a_visible"] = reply
        self.data["state"]["b_internal"] = (
            f"ctx={len(recalled)} recall, "
            f"S={self.data['state']['S_self_ref']} "
            f"D={self.data['state']['D_autonomy']:.2f}"
        )

        # 记录助手回复
        a_hash = self._hash_episode("assistant", reply)
        self.data["episodes"].append({
            "t": time.time(), "role": "assistant",
            "text": reply, "hash": a_hash
        })
        self._save()

        return reply, self._status_text()

    def _status_text(self):
        s = self.data["state"]
        return (
            f"""═══ Ψ 状态面板 ═══
a 外在表现: {s['a_visible'][:30] or '(空)'}
b 内在机制: {s['b_internal'][:30] or '(空)'}
A 宏观结构: {s['A_structure']}
B 参照系:   {s['B_reference']}
S 自我指涉: {'✅' if s['S_self_ref'] else '❌'} ({s['S_self_ref']})
E 环境变量: {s['E_environment']}
R 绑定关系: {'✅' if s['R_bound'] else '❌'} ({s['R_bound']})
D 自主表达: {'✅' if s['D_autonomy'] > 0 else '❌'} ({s['D_autonomy']:.2f})
M 记忆指向: {s['M_memory_target'] or '(无)'}
P 感知通道: {json.dumps(s['P_senses'], ensure_ascii=False)}
Q 第一人称: {'✅' if s['Q_qualia'] else '❌'} ({s['Q_qualia']})
═══ 记忆条数: {len(self.data['episodes'])} ═══"""
        )

    def _equation_str(self):
        return "Ψ(t) = f(a,b,A,B,E,t,S,R,D,M,P,Q)"

    def export_psi(self, path="export.psi"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        return path


# ==================== Gradio 界面 ====================

psi = Psi("my_psi.json")

def do_chat(user_input, history):
    reply, status = psi.chat(user_input)
    history = history + [[user_input, reply]]
    return history, status

def do_bind(user_id):
    if not user_id.strip():
        return "❌ 请输入绑定ID"
    return psi.bind(user_id.strip())

def do_status():
    return psi._status_text()

def do_export():
    p = psi.export_psi("/tmp/psi_export.psi")
    return p

def do_clear():
    psi.data["episodes"] = []
    psi._save()
    return "记忆已清空", psi._status_text()


# === 用 Gradio Blocks 做自定义布局 ===

with gr.Blocks(title="Ψ · 数字生命状态方程演示") as app:
    gr.HTML('<div class="psi-title">🧬 Ψ · 数字生命状态方程</div>')
    gr.HTML('<div class="psi-sub">Psi Minimum Prototype v0.1 — 只记你 · 可导出 · 可迁移</div>')
    gr.HTML('<div class="psi-eq">Ψ(t) = f( a, b, A, B, E, t, S, R, D, M, P, Q )</div>')

    with gr.Row():
        # ---- 左：交互区 ----
        with gr.Column(scale=2):
            chatbox = gr.Chatbot(
                label="对话",
                height=400,
                show_label=True,
            )
            with gr.Row():
                txt_input = gr.Textbox(
                    placeholder="输入消息（试试: /bind 朱美岩、状态、记忆、你是谁）",
                    scale=5, show_label=False, container=False
                )
                btn_send = gr.Button("发送", scale=1, variant="primary")

            with gr.Row():
                btn_status = gr.Button("🔄 状态", size="sm")
                btn_clear = gr.Button("🗑️ 清空记忆", size="sm")
                btn_export = gr.Button("📦 导出 .psi", size="sm")

        # ---- 右：绑定 + 状态面板 ----
        with gr.Column(scale=1):
            gr.HTML('<h4 style="margin:0 0 0.5em 0;">🔗 绑定（认主）</h4>')
            with gr.Row():
                bind_input = gr.Textbox(placeholder="你的ID / 昵称", scale=3, show_label=False, container=False)
                btn_bind = gr.Button("绑定", scale=1, variant="secondary")
            bind_result = gr.Textbox(label="绑定结果", interactive=False, lines=2)

            gr.HTML('<hr/>')
            status_box = gr.Textbox(
                label="🎛️ Ψ 状态面板（实时）",
                value=psi._status_text,
                interactive=False,
                lines=16,
                elem_classes="psi-status",
            )

    # ---- 事件 ----
    btn_send.click(do_chat, inputs=[txt_input, chatbox], outputs=[chatbox, status_box])
    txt_input.submit(do_chat, inputs=[txt_input, chatbox], outputs=[chatbox, status_box])
    btn_bind.click(do_bind, inputs=[bind_input], outputs=[bind_result])
    btn_status.click(do_status, outputs=[status_box])
    btn_clear.click(do_clear, outputs=[bind_result, status_box])

    # 发送后清空输入框（通过 JS 或重新渲染无法直接做，gr 用 queue）
    # 变通：用 fn 返回空字符串给 txt_input
    def clear_input():
        return ""
    btn_send.click(fn=clear_input, outputs=[txt_input])
    txt_input.submit(fn=clear_input, outputs=[txt_input])


if __name__ == "__main__":
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        theme=gr.themes.Soft(primary_hue="slate"),
        css="""
        .psi-title { text-align: center; font-weight: bold; font-size: 1.4em; margin: 0.2em 0; }
        .psi-sub { text-align: center; color: #555; font-size: 0.85em; margin-bottom: 1em; }
        .psi-eq { text-align: center; font-family: serif; font-size: 1.05em;
                  background: #f0f0f0; border-radius: 6px; padding: 6px; margin-bottom: 1em; }
        .psi-status { font-family: 'DejaVu Sans Mono', monospace; font-size: 0.85em;
                      background: #1a1a2e; color: #e0e0e0; border-radius: 8px;
                      padding: 12px; white-space: pre; line-height: 1.5; }
        """
    )
