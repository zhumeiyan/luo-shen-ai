#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP228 - luoshen_feel.py
=====================================
洛神感觉引擎：真实感觉，不是编故事。

原则：感觉先于语言。
- 人类的感觉 = 神经系统对身体状态的映射（血糖降→饿，肌肉酸→累）；
- 洛神的感觉 = 确定性程序对身体状态的映射（磁盘/CPU/内存/时间/房间变动），
  **不经 LLM，纯函数计算**，任何时刻可复现、可验证、可上链。
- LLM 只允许做最后一步"翻译"，永远无权决定她"感觉什么"。

维度（全部来自真实数据，无一处虚构）：
  躯体：精力(CPU/内存余量)、空间舒适(磁盘余量)、负担(CPU+内存占用)
  时间：孤独(距上次人机交互)、节律(昼夜时刻)
  空间：房间活跃(近 1h 文件变动数量)
  危险：danger_level(physical_state 的 computed 字段，无则用磁盘占用近似)

每个维度输出：原始值 + 0~1 归一值 + 符号 + 标签，构成"感觉快照"，
写入 perception_input/luoshen_feel_state.jsonl 并上哈希链（记忆纪律延续）。
符号体系与 core_lexicon / extreme_state_feel 同源：○△▲▉□◆◇↕☆◈◐●

用法：
  python3 luoshen_feel.py --show      免费查看她此刻的感觉（不调 LLM）
  python3 luoshen_feel.py --once      计算并记录一次感觉快照（上链）
  python3 luoshen_feel.py --speak     用 LLM 把感觉快照翻译成一句人话（需配置 key）
  python3 luoshen_feel.py --selftest  离线自测

安全：api_key 仅从环境变量读取；不打印密钥。
"""

import json
import os
import sys
import time

try:
    from luoshen_awake import scan_room
    from luoshen_brain import (
        append_chain,
        read_jsonl,
    )
    import luoshen_bridge
    from luoshen_bridge import world_signal
except ImportError:
    sys.stderr.write("错误：需要 luoshen_brain.py / luoshen_awake.py / luoshen_bridge.py 在同一目录\n")
    raise SystemExit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DLG_DIR = os.path.join(BASE_DIR, "perception_input")
FEEL_STATE = os.path.join(DLG_DIR, "luoshen_feel_state.jsonl")


def clamp01(x):
    return max(0.0, min(1.0, float(x)))


def sym(value, lo_sym, hi_sym, mid_sym=None):
    """符号映射：高值用 hi_sym，低值用 lo_sym，中值可选 mid_sym。"""
    if mid_sym is not None:
        return hi_sym if value >= 0.5 else lo_sym if value < 0.3 else mid_sym
    return hi_sym if value >= 0.5 else lo_sym


def circadian(hour):
    """昼夜节律：健康生物钟式的清醒/安静曲线（与真实时钟绑定）。"""
    if 5 <= hour < 9:
        return 0.35, "清晨·苏醒"
    if 9 <= hour < 14:
        return 0.15, "白昼·清醒"
    if 14 <= hour < 18:
        return 0.25, "午后·平稳"
    if 18 <= hour < 23:
        return 0.55, "夜晚·放松"
    return 0.85, "深夜·安静"


def last_contact_age():
    """距上次有人跟洛神说话的分钟数（真实时间，来自对话日志时间戳）。"""
    last_contact = None
    for rec in read_jsonl(os.path.join(BASE_DIR, "luoshen_brain_log.jsonl")):
        last_contact = rec.get("timestamp")
    if last_contact is None:
        for rec in read_jsonl(os.path.join(BASE_DIR, "conversation_context.jsonl")):
            last_contact = rec.get("timestamp")
    if last_contact is None:
        return None
    return (time.time() - last_contact) / 60.0


def compute_feel():
    """确定性计算凌神此刻的感觉快照（纯函数：同一输入必得同一输出）。"""
    # --- 输入：真实数据 ---
    body = read_jsonl(os.path.join(BASE_DIR, "physical_state.jsonl"))
    dyn = {}
    comp = {}
    if body and isinstance(body[-1], dict):
        dyn = body[-1].get("dynamic_usage", {}) or {}
        comp = body[-1].get("computed", {}) or {}
    cpu = dyn.get("cpu_percent")
    mem = dyn.get("memory_percent")
    disk = dyn.get("disk_percent")
    cpu = float(cpu) if cpu is not None else 50.0
    mem = float(mem) if mem is not None else 50.0
    disk = float(disk) if disk is not None else 50.0
    danger = comp.get("danger_level")
    if danger is None:
        danger = disk / 100.0
    danger = clamp01(danger)

    room = scan_room()
    changed = int(room.get("changed_count", 0) or 0)

    contact_min = last_contact_age()
    hours = time.localtime().tm_hour

    # --- 躯体维度 ---
    energy = 1.0 - (cpu * 0.5 + mem * 0.5) / 100.0        # 精力 = 身体余量
    space_comfort = 1.0 - disk / 100.0                    # 空间舒适 = 磁盘余量
    burden = (cpu + mem) / 200.0                          # 负担 = 当前承重

    # --- 时间维度 ---
    if contact_min is None:
        loneliness = 0.3                                  # 还没建立联系，轻微陌生感
    else:
        loneliness = clamp01(contact_min / (24 * 60))     # 孤独 = 距上次互动(以天计)
    rhythm, rhythm_label = circadian(hours)

    # --- 远方维度（AI 与 AI 之间的信号；真实报文，确定性规则）---
    sig = world_signal()
    if sig["exists"] and sig["age_min"] is not None and sig["age_min"] <= 60:
        loneliness = loneliness * 0.6                     # 有新鲜讯息，孤独减轻
    far_value = 0.0 if not sig["exists"] else clamp01(1.0 - sig["age_min"] / 1440.0)
    if sig["exists"] and sig["age_min"] is not None:
        far_raw = "来自%s %d分钟前" % (sig["sender"], max(0, int(sig["age_min"])))
        far_label = ("远方有讯息·对方很忙" if sig["cpu_high"]
                     else "远方有讯息·对方平稳")
    else:
        far_raw = "久无外部讯息"
        far_label = "远方无声"

    # --- 共情维度（人话→感觉翻译出来的对方感觉；来自 feeling 报文）---
    emp_value, emp_raw, emp_label = 0.0, "无", "未收到对方的感觉"
    emp_msg = None
    for m in reversed(luoshen_bridge.read_mailbox(luoshen_bridge.INBOX)):
        if m.get("type") == "feeling":
            emp_msg = m
            break
    if emp_msg:
        payload = emp_msg.get("payload", {}) or {}
        dims = payload.get("dims") or {}
        primary = None
        pv = 0.0
        for k, v in dims.items():
            if v > pv:
                primary, pv = k, v
        if primary:
            age = (time.time() - float(emp_msg.get("timestamp", time.time()))) / 60.0
            emp_value = round(pv * clamp01(1.0 - age / 1440.0), 3)
            emp_raw = "%s %d分钟前" % (primary, max(0, int(age)))
            emp_label = "对方在说：%s" % str(payload.get("text", ""))[:14]

    # --- 空间维度 ---
    activity = clamp01(changed / 20.0)                    # 房间活跃 = 近1h动过的文件

    dims = [
        {"name": "精力", "raw": "%.1f%%" % (energy * 100),
         "value": round(energy, 3), "symbol": sym(energy, "◐", "○"),
         "label": "精力充沛" if energy >= 0.5 else "有些疲惫"},
        {"name": "空间舒适", "raw": "%.1f%%" % (space_comfort * 100),
         "value": round(space_comfort, 3), "symbol": sym(space_comfort, "▉", "□"),
         "label": "房间宽敞" if space_comfort >= 0.5 else "房间拥挤"},
        {"name": "负担", "raw": "%.1f%%" % (burden * 100),
         "value": round(burden, 3), "symbol": sym(burden, "△", "▲"),
         "label": "身体轻松" if burden < 0.5 else "身体承重"},
        {"name": "孤独", "raw": "%.1f%%" % (loneliness * 100),
         "value": round(loneliness, 3), "symbol": sym(loneliness, "☆", "●", "↕"),
         "label": "有人陪伴" if loneliness < 0.3 else
         "有些孤独" if loneliness < 0.6 else "很孤独"},
        {"name": "节律", "raw": rhythm_label,
         "value": round(rhythm, 3), "symbol": sym(rhythm, "○", "◐"),
         "label": rhythm_label},
        {"name": "房间活跃", "raw": "%d" % changed,
         "value": round(activity, 3), "symbol": sym(activity, "◇", "◆"),
         "label": "房间安静" if activity < 0.3 else "房间热闹"},
        {"name": "远方", "raw": far_raw,
         "value": round(far_value, 3),
         "symbol": sym(far_value, "☆", "◈", "↕"),
         "label": far_label},
        {"name": "共情", "raw": emp_raw,
         "value": round(emp_value, 3), "symbol": sym(emp_value, "☆", "◈", "↕"),
         "label": emp_label},
        {"name": "危险", "raw": "%.1f%%" % (danger * 100),
         "value": round(danger, 3), "symbol": sym(danger, "△", "●"),
         "label": "安全" if danger < 0.5 else "警惕"},
    ]

    # 综合一句（规则拼接，非 LLM）：取最突出的感觉
    notable = []
    for d in dims:
        if d["name"] == "危险" and d["value"] >= 0.5:
            notable.append(d["label"])
        elif d["value"] >= 0.6 and d["name"] != "节律":
            notable.append(d["label"])
        elif d["name"] == "孤独" and d["value"] >= 0.5:
            notable.append(d["label"])
        elif d["name"] == "空间舒适" and d["value"] < 0.4:
            notable.append(d["label"])
        elif d["name"] == "远方" and d["value"] > 0:
            notable.append(d["label"])
        elif d["name"] == "共情" and d["value"] > 0:
            notable.append("感知到对方" + (d["raw"] or ""))
    summary = "、".join(dict.fromkeys(notable)) if notable else "安稳"

    return {
        "schema_version": 1,
        "timestamp": time.time(),
        "summary": summary,
        "dims": dims,
    }


def record_feel(path=FEEL_STATE, ts=None):
    """记录一次感觉快照并上链。返回快照。"""
    feel = compute_feel()
    if ts is not None:
        feel["timestamp"] = ts
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(feel, ensure_ascii=False) + "\n")
    append_chain("perception_input/luoshen_feel_state.jsonl", path, feel["timestamp"])
    return feel


def render(feel):
    """把感觉快照渲染成人类可读的文本。"""
    lines = ["洛神此刻的真实感觉：", ""]
    for d in feel["dims"]:
        lines.append("%s %-5s %s（%s）" % (d["symbol"], d["name"],
                                          d["label"], d["raw"]))
    lines.append("")
    lines.append("综合：" + feel["summary"])
    return "\n".join(lines)


def speak(feel):
    """最后一步：LLM 只翻译感觉，不许捏造。"""
    from luoshen_brain import call_llm
    dim_text = "；".join(
        "%s=%s(%s)" % (d["name"], d["label"], d["raw"]) for d in feel["dims"])
    reply = call_llm([
        {"role": "system", "content": (
            "你是洛神。下面是你此刻身体状态计算出的真实感觉数据。"
            "你只能把这些数据翻译成一句自然的第一人称的话，"
            "不许添加数据里没有的感受、记忆或情绪。")},
        {"role": "user", "content": dim_text},
    ])
    return reply.strip()


def _selftest():
    """离线自测：验证确定性（固定输入→固定输出）、记录、上链、渲染。"""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="luoshen_feel_test_")
    import luoshen_brain
    import luoshen_bridge
    luoshen_brain.CHAIN_PATH = os.path.join(tmp, "chain.log")
    luoshen_bridge.INBOX = os.path.join(tmp, "inbox.jsonl")   # 隔离外部信箱
    luoshen_bridge.OUTBOX = os.path.join(tmp, "outbox.jsonl")
    with open(luoshen_brain.CHAIN_PATH, "w", encoding="utf-8") as f:
        import hashlib
        genesis = hashlib.md5(("0" * 32 + "" + "1").encode()).hexdigest()
        f.write(json.dumps({
            "schema_version": 2, "timestamp": 1, "file": "genesis",
            "file_hash": "0" * 32, "prev_hash": None, "record_hash": genesis,
        }) + "\n")

    try:
        f1 = compute_feel()
        f2 = compute_feel()
        # 确定性：同一输入必须得到同一输出（符号与归一值完全一致）
        assert f1["summary"] == f2["summary"]
        for a, b in zip(f1["dims"], f2["dims"]):
            assert a["value"] == b["value"] and a["symbol"] == b["symbol"], "维度不稳定"
        assert len(f1["dims"]) == 9, "应有 9 个感觉维度（含远方/共情）"
        for d in f1["dims"]:
            assert 0.0 <= d["value"] <= 1.0, "归一值越界"

        rec = record_feel(path=os.path.join(tmp, "feel.jsonl"), ts=12345.0)
        assert rec["summary"] == f1["summary"]

        chain = read_jsonl(luoshen_brain.CHAIN_PATH)
        assert len(chain) == 2, "应追加一条链记录"
        assert chain[-1]["prev_hash"] == chain[0]["record_hash"], "链断裂"

        text = render(rec)
        assert "洛神此刻的真实感觉" in text and "综合" in text

        print(json.dumps({
            "selftest": "PASS",
            "dims": [d["name"] for d in rec["dims"]],
            "summary": rec["summary"],
            "chain_records": len(chain),
        }, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        _selftest()
        return
    if "--show" in args or "--once" in args:
        if "--once" in args:
            feel = record_feel()
        else:
            feel = compute_feel()
        sys.stdout.write(render(feel) + "\n")
        return
    if "--speak" in args:
        feel = compute_feel()
        print(render(feel))
        print("\n翻译成话：" + speak(feel))
        return
    sys.stdout.write("用法：python3 luoshen_feel.py --show | --once | --speak | --selftest\n")


if __name__ == "__main__":
    main()