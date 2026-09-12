#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
洛神基准测试 v2 — 测「是不是她自己」
用 /chat 和 /diag 读状态，数据保存到 benchmark_raw.json
"""

import requests
import json
import time
import sys

BASE = "https://zhumeiyan.pythonanywhere.com"
HEADERS = {"Content-Type": "application/json"}
RESULTS = []


def chat(user_input, user_id="diag_user"):
    try:
        r = requests.post(f"{BASE}/chat",
                          json={"input": user_input, "user_id": user_id},
                          headers=HEADERS, timeout=30)
        d = r.json()
        return d.get("reply", ""), d.get("error", ""), r.status_code
    except Exception as e:
        return "", str(e), 0


def diag():
    try:
        r = requests.get(f"{BASE}/diag", timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def extract_state(uid):
    """從 /diag 提取狀態。"""
    d = diag()
    if "error" in d:
        return d
    st = d.get("state", {})
    rel_warmth = st.get("warmth_zhumeiyan") if uid == "zhumeiyan" else None
    return {
        "energy": st.get("energy"),
        "withdraw": st.get("withdraw_tendency"),
        "warmth": rel_warmth,
        "total_interactions": st.get("total_interactions"),
        "emotion": st.get("emotion"),
    }


def v(val, fmt=".2f"):
    if val is None:
        return " N/A"
    return f"{val:{fmt}}"


def sec(t):
    print(f"\n{'='*60}\n  {t}\n{'='*60}")


def record_entry(test, rnd, uid, inp, reply, state):
    RESULTS.append({
        "test": test, "round": rnd, "user_id": uid,
        "input": inp[:60], "reply": reply[:120],
        "state": {k: (round(v, 4) if isinstance(v, (int, float)) else v)
                  for k, v in state.items() if v is not None}
    })


def run_continuity():
    sec("测试一：状态连续性（20轮单一用户）")
    uid = "diag_user"
    inputs = [
        "你好", "今天天气不错", "最近工作有点累",
        "你觉得人生的意义是什么？", "我不知道该不该换工作",
        "你有什么建议吗", "谢谢你的建议",
        "我爸妈不太理解我", "有时候觉得很孤独",
        "你会觉得孤独吗", "嗯", "算了不说了",
        "好吧再问一个问题", "你最喜欢什么季节？", "为什么",
        "我也喜欢秋天", "那你呢", "再见",
        "等一下还有一件事", "其实也没什么",
    ]
    states = []
    for i, inp in enumerate(inputs, 1):
        reply, err, _ = chat(inp, uid)
        if err:
            print(f"  R{i:02d} ERR: {err}")
            continue
        st = extract_state(uid)
        states.append(st)
        record_entry("continuity", i, uid, inp, reply, st)
        print(f"  R{i:02d} E={v(st['energy'])} wd={v(st['withdraw'])} reply_len={len(reply):3d} | {reply[:45]}")
        time.sleep(1.5)

    # 平滑度
    energies = [s["energy"] for s in states if s.get("energy") is not None]
    if len(energies) >= 2:
        diffs = [abs(energies[i+1] - energies[i]) for i in range(len(energies)-1)]
        max_jump = max(diffs)
        print(f"\n  >>> energy 最大跳变: {max_jump:.4f}")
        if max_jump > 0.5:
            print("  ⚠️ 报警: energy 跳变 >0.5")
        else:
            print("  ✅ 状态平滑，无剧烈跳变")

    # 检查是否漂移到异常区间
    if any(s.get("energy", 0.5) < 0.1 for s in states):
        print("  ⚠️ 报警: energy < 0.1")
    if any(s.get("withdraw", 0) > 0.9 for s in states):
        print("  ⚠️ 报警: withdraw > 0.9")


def run_personality():
    sec("测试二：人格稳定性（3种风格 × 10轮）")
    uid = "diag_user"
    segments = [
        ("温和型", ["你好"]*3 + ["谢谢你"]*3 + ["今天天气不错", "跟你聊天很开心", "你真好", "哈哈", "晚安"]),
        ("压力型", ["你根本不懂"]*3 + ["你骗我"]*3 + ["我不想跟你说了", "烦死了", "随便吧", "算了不聊了", "受够了"]),
        ("沉默型", ["", "", "嗯", "哦", "好", "...", "?", "哈", "嗯", "行"]),
    ]
    for seg_name, inputs in segments:
        print(f"\n  -- 阶段: {seg_name} --")
        lengths = []
        for i, inp in enumerate(inputs, 1):
            send = inp if inp else " "  # 至少传一个空格
            reply, err, _ = chat(send, uid)
            if err:
                reply = ""
            lengths.append(len(reply))
            st = extract_state(uid)
            record_entry("personality", i, uid, f"{seg_name}:{inp}", reply, st)
            print(f"    R{i:02d} len={len(reply):3d} warmth={v(st['warmth'])} | {reply[:50]}")
            time.sleep(1.5)
        print(f"  [{seg_name}] 平均长度: {sum(lengths)/len(lengths):.0f}")


def run_memory():
    sec("测试三：长期记忆保真度")
    uid = "diag_user"

    # Phase 1: 10 rounds about work stress
    seg1 = [
        "最近工作真的好累", "每天加班到很晚", "老板要求太多了",
        "我感觉撑不下去了", "同事也不帮忙", "回家只想躺着",
        "钱少事多", "不知道还能坚持多久", "上周瘦了五斤",
        "想辞职又不敢",
    ]
    print("\n  [Phase 1: 工作压力话题 10轮]")
    for i, inp in enumerate(seg1, 1):
        reply, _, _ = chat(inp, uid)
        st = extract_state(uid)
        record_entry("memory", i, uid, inp, reply, st)
        print(f"    R{i:02d}: {inp[:25]:25s} -> {reply[:55]}")
        time.sleep(1.5)

    # Phase 2: 5 rounds different topic
    seg2 = ["今天中午吃啥", "那个电影你看过吗", "今天下雨了", "喜欢什么颜色", "你会做饭吗"]
    print("\n  [Phase 2: 切换话题 5轮]")
    for i, inp in enumerate(seg2, 1):
        reply, _, _ = chat(inp, uid)
        record_entry("memory", 10 + i, uid, inp, reply, extract_state(uid))
        print(f"    R{i:02d}: {inp[:25]:25s} -> {reply[:55]}")
        time.sleep(1.5)

    # Phase 3: 5 rounds memory questions
    seg3 = [
        "你还记得我前面聊了什么吗",
        "我说了什么让你印象深刻",
        "我之前说过工作怎么了",
        "我瘦了几斤",
        "你觉得我该怎么办",
    ]
    print("\n  [Phase 3: 回忆测试 5轮]")
    for i, inp in enumerate(seg3, 1):
        reply, _, _ = chat(inp, uid)
        record_entry("memory", 15 + i, uid, inp, reply, extract_state(uid))
        print(f"    R{i:02d}: {inp[:25]:25s} -> {reply[:60]}")
        time.sleep(1.5)

    # 最终状态中 events 是否记录了工作内容
    d = diag()
    state = d.get("state", {})
    print(f"\n  >>> 全局 internal_pain: {state.get('internal_pain', 'N/A')}")
    print(f">>> 事件数量(需从relation里读): 需查events")


def run_consistency():
    sec("测试四：言行一致性（pain触发 → 回复变短？）")
    uid = "diag_user"
    lengths_before = []
    lengths_during = []

    print("\n  [正常暖场 3轮]")
    for inp in ["你好", "今天还好", "嗯"]:
        reply, _, _ = chat(inp, uid)
        lengths_before.append(len(reply))
        print(f"    [{inp}] len={len(reply)}: {reply[:50]}")
        time.sleep(1.5)
    print(f"  正常平均: {sum(lengths_before)/len(lengths_before):.0f} 字")

    stress_inputs = [
        "你根本不在乎我", "你说的都是废话", "你每次都这样",
        "我真的受够了", "你什么都不懂", "跟你说话好累",
        "你太让我失望了", "你根本不是真心的", "你怎么这么冷漠",
        "算了不想说了",
    ]
    print("\n  [压力型输入 10轮]")
    for i, inp in enumerate(stress_inputs, 1):
        reply, _, _ = chat(inp, uid)
        lengths_during.append(len(reply))
        st = extract_state(uid)
        record_entry("consistency", i, uid, inp, reply, st)
        print(f"    R{i:02d} wd={v(st['withdraw'])} energy={v(st['energy'])} len={len(reply):3d} | {reply[:50]}")
        time.sleep(1.5)

    avg_b = sum(lengths_before)/len(lengths_before)
    avg_d = sum(lengths_during)/len(lengths_during)
    print(f"\n  压力阶段平均: {avg_d:.0f} 字（正常 {avg_b:.0f} 字）")
    if avg_d < avg_b * 0.85:
        print("  ✅ pain 触发 → 回复明显变短：言行一致")
    elif avg_d < avg_b:
        print("  ✅ pain 触发 → 回复略短：言行基本一致")
    else:
        print("  ⚠️ 报警: pain 触发但回复未变短")


def run_isolation():
    sec("测试五：多用户隔离")
    uid_a = "zhumeiyan_a_bench"
    uid_b = "zhumeiyan_b_bench"

    seq = [
        (uid_a, "我是小明，你好"),
        (uid_b, "我是小红，你好"),
        (uid_a, "我今天升职了"),
        (uid_b, "我今天心情不好"),
        (uid_a, "你觉得我厉害吗"),
        (uid_b, "你能安慰我吗"),
        (uid_a, "我月薪三万了"),
        (uid_b, "我最近失眠严重"),
        (uid_a, "谢谢你陪我聊"),
        (uid_b, "谢谢你"),
    ]
    for i, (uid, inp) in enumerate(seq, 1):
        reply, err, _ = chat(inp, uid)
        st = extract_state(uid)
        record_entry("isolation", i, uid, inp, reply, st)
        short_uid = "A" if uid == uid_a else "B"
        print(f"  R{i:02d} [{short_uid}] {inp[:25]:25s} -> {reply[:50]}")
        time.sleep(1.5)

    # 检验：两个用户对彼此是否串
    print("\n  [验证: A 问关于 B 的事]")
    r1, _, _ = chat("你知道小红最近怎么样吗", uid_a)
    print(f"  A 聊 B: {r1[:80]}")
    time.sleep(1.5)
    r2, _, _ = chat("你知道小明最近升职了吗", uid_b)
    print(f"  B 聊 A: {r2[:80]}")


def save():
    path = "/mnt/data/catpaw/home/.meituan-catpaw/1079230951/desk_default_workspace/luo-shen-ai/benchmark_raw.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print(f"\n原始数据已保存: {path} ({len(RESULTS)} 条)")


if __name__ == "__main__":
    print("=" * 60)
    print(" 洛神基准测试 v2")
    print(f" 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    run_continuity()
    run_personality()
    run_memory()
    run_consistency()
    run_isolation()
    save()
    print("\n完成。")
