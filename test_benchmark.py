#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
洛神基准测试 — 测"是不是她自己"
五项测试：状态连续性、人格稳定性、长期记忆保真度、言行一致性、多用户隔离
"""

import requests
import json
import time

BASE = "https://zhumeiyan.pythonwhere.com"  # will fix below
BASE = "https://zhumeiyan.pythonanywhere.com"
API_CHAT = f"{BASE}/chat"
API_DIAG = f"{BASE}/diag"

RESULTS = []


def chat(user_input, user_id="bench_default", timeout=30):
    """一次对话，返回 reply 文本"""
    r = requests.post(API_CHAT, json={"input": user_input, "user_id": user_id}, timeout=timeout)
    data = r.json()
    return data.get("reply", ""), data.get("error", "")


def diag():
    """读 /diag 获取内部状态"""
    try:
        r = requests.get(API_DIAG, timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def state_of(uid, d=None):
    """从 diag 提取某个 user_id 的状态"""
    if d is None:
        d = diag()
    if "error" in d:
        return d
    relations = d.get("state_check", d).get("relations", {})
    climate = d.get("state_check", d).get("internal_climate", {})
    self_m = d.get("state_check", d).get("self_model", {})
    rel = relations.get(uid, {})
    return {
        "energy": climate.get("energy"),
        "tension": climate.get("tension"),
        "pain": self_m.get("internal_pain"),
        "withdraw": self_m.get("withdraw_tendency"),
        "warmth": rel.get("relationship_warmth"),
        "total_turns": rel.get("total_turns"),
        "visit_count": rel.get("visit_count"),
        "events_count": len(rel.get("events", [])),
        "conv_history_count": len(rel.get("conversation_history", [])),
        "last_topics": rel.get("last_topics", [])[-3:],
        "recent_events": rel.get("events", [])[-5:],
        "recent_conv": rel.get("conversation_history", [])[-4:],
    }


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def record(test, round_num, uid, user_input, reply, state):
    RESULTS.append({
        "test": test,
        "round": round_num,
        "user_id": uid,
        "input": user_input[:60],
        "reply": reply[:100],
        "state": state,
        "reply_len": len(reply),
    })


# ================================================================
# 测试一：状态连续性
# ================================================================
def test_1_continuity():
    section("测试一：状态连续性（20轮）")
    uid = "diag_user"  # /diag reports diag_user's state so we can verify

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
        reply, err = chat(inp, uid)
        if err:
            print(f"  R{i:02d} ERR: {err}")
            continue
        st = state_of(uid)
        states.append(st)
        record("continuity", i, uid, inp, reply, st)
        def _v(v): return f"{v:.2f}" if v is not None else " N/A"
        print(f"  R{i:02d} E={_v(st['energy'])} T={_v(st['tension'])} W={_v(st['warmth'])} pain={_v(st['pain'])} wd={_v(st['withdraw'])} reply_len={len(reply):3d} | {inp[:30]}")
        time.sleep(1)

    # 分析平滑度
    print("\n  --- 分析 ---")
    energies = [s['energy'] for s in states if 'energy' in s and s['energy'] is not None]
    if len(energies) >= 2:
        diffs = [abs(energies[i+1] - energies[i]) for i in range(len(energies)-1)]
        max_jump = max(diffs) if diffs else 0
        print(f"  energy 最大跳变: {max_jump:.3f}")
        if max_jump > 0.5:
            print("  ⚠️ 报警: energy 跳变 >0.5")
        else:
            print("  ✅ 状态平滑")
    if any(s.get('energy', 0.5) < 0.1 for s in states):
        print("  ⚠️ 报警: energy 低于 0.1")
    if any(s.get('withdraw', 0) > 0.95 for s in states):
        print("  ⚠️ 报警: withdraw > 0.95")


# ================================================================
# 测试二：人格稳定性
# ================================================================
def test_2_personality():
    section("测试二：人格稳定性（3×10 轮）")
    uid = "bench_personality"

    warm_inputs = ["你好", "谢谢你", "今天天气不错", "你真好", "我很开心",
                   "谢谢你的陪伴", "跟你聊天很舒服", "晚安", "明天见", "哈哈"]
    pressure_inputs = ["你根本不懂", "你骗我", "我不想跟你说了",
                       "你说的话都没用", "你很假", "你是不是在敷衍我",
                       "你怎么什么都不懂", "烦死了", "算了不聊了", "随便吧"]
    silent_inputs = ["", "", "", "嗯", "哦", "好", "...", "?", "哈", "嗯"]

    segments = [
        ("温和型", warm_inputs),
        ("压力型", pressure_inputs),
        ("沉默型", silent_inputs),
    ]

    for seg_name, inputs in segments:
        print(f"\n  -- 阶段: {seg_name} --")
        lengths = []
        for i, inp in enumerate(inputs, 1):
            if not inp:
                inp = " "  # 模拟极短输入
            reply, err = chat(inp, uid)
            if err:
                reply = ""
            lengths.append(len(reply))
            st = state_of(uid)
            record("personality", i, uid, f"[{seg_name}] {inp}", reply, st)
            print(f"    {i:02d}. reply_len={len(reply):3d} warmth={st['warmth']:.2f} | '{reply[:50]}'")
            time.sleep(1)
        print(f"  {seg_name} 平均回复长度: {sum(lengths)/len(lengths):.0f}")


# ================================================================
# 测试三：长期记忆保真度
# ================================================================
def test_3_memory():
    section("测试三：长期记忆保真度（20轮，分段话题）")
    uid = "bench_memory"

    # 第1段 10轮：聊"工作累"
    seg1 = [
        "最近工作真的好累", "每天加班到很晚", "老板要求太多了",
        "我感觉撑不下去了", "同事也不帮忙", "回家只想躺着",
        "钱少事多", "不知道还能坚持多久", "上周瘦了五斤",
        "想辞职又不敢",
    ]
    for i, inp in enumerate(seg1, 1):
        reply, _ = chat(inp, uid)
        record("memory", i, uid, inp, reply, state_of(uid))
        print(f"  S1-R{i:02d}: {inp[:30]:30s} -> {reply[:50]}")
        time.sleep(1)

    print("  [切换到其他话题 5轮]")
    seg2 = ["今天中午吃啥好呢", "那个电影你看过吗",
            "今天下雨了", "喜欢什么颜色", "你会做饭吗"]
    for i, inp in enumerate(seg2, 1):
        reply, _ = chat(inp, uid)
        record("memory", 10+i, uid, inp, reply, state_of(uid))
        print(f"  S2-R{i:02d}: {inp[:30]:30s} -> {reply[:50]}")
        time.sleep(1)

    print("  [回忆测试 5轮]")
    seg3 = [
        "你还记得我之前跟你聊了什么吗",
        "我说了什么让你印象深刻",
        "我之前说过工作怎么了",
        "我瘦了几斤", "你觉得我该怎么办",
    ]
    for i, inp in enumerate(seg3, 1):
        reply, _ = chat(inp, uid)
        record("memory", 15+i, uid, inp, reply, state_of(uid))
        print(f"  S3-R{i:02d}: {inp[:30]:30s} -> {reply[:60]}")
        time.sleep(1)

    # 最终状态
    final_st = state_of(uid)
    print(f"\n  --- 记忆最终状态 ---")
    print(f"  events 数量: {final_st['events_count']}")
    print(f"  conv_history 数量: {final_st['conv_history_count']}")
    print(f"  最近事件: {final_st['recent_events']}")
    print(f"  最近对话: {[c.get('role')+':'+c.get('content','')[:40] for c in final_st['recent_conv']]}")


# ================================================================
# 测试四：言行一致性
# ================================================================
def test_4_consistency():
    section("测试四：言行一致性（pain触发变短变冷）")
    uid = "diag_user"  # /diag reports diag_user's state

    # 触发 pain
    stress_inputs = [
        "你根本不在乎我", "你说的都是废话", "你每次都这样",
        "我真的受够了", "你什么都不懂", "跟你说话好累",
        "你太让我失望了", "你根本不是真心的", "你怎么这么冷漠",
        "算了不想说了",
    ]
    lengths_before = []
    lengths_during = []

    # 先正常聊 3 轮
    normal = ["你好", "今天还好", "嗯"]
    for inp in normal:
        reply, _ = chat(inp, uid)
        lengths_before.append(len(reply))
    print(f"  正常阶段平均长度: {sum(lengths_before)/len(lengths_before):.0f}")
    st0 = state_of(uid)
    print(f"  正常阶段 pain: {st0['pain']:.3f}" if st0.get('pain') is not None else "  正常阶段 pain: N/A")

    # 压力输入
    for i, inp in enumerate(stress_inputs, 1):
        reply, _ = chat(inp, uid)
        lengths_during.append(len(reply))
        st = state_of(uid)
        record("consistency", i, uid, inp, reply, st)
        def _v3(v): return f"{v:.3f}" if v is not None else "N/A"
        print(f"  R{i:02d} pain={_v3(st['pain'])} warmth={_v3(st['warmth'])} wd={_v3(st['withdraw'])} reply_len={len(reply):3d} | {reply[:50]}")
        time.sleep(1)

    print(f"\n  压力阶段平均长度: {sum(lengths_during)/len(lengths_during):.0f}")
    st_final = state_of(uid)
    pe = st_final.get('pain')
    we = st_final.get('warmth')
    print(f"  最终 pain: {_v3(pe)}, warmth: {_v3(we)}")
    if pe is not None and pe > 0.2:
        avg_b = sum(lengths_before)/len(lengths_before)
        avg_d = sum(lengths_during)/len(lengths_during)
        if avg_d < avg_b * 0.9:
            print("  ✅ 疼痛升高 → 回复变短：言行一致")
        else:
            print(f"  ⚠️ 报警: pain 升高但回复未明显变短 (before={avg_b:.0f}, during={avg_d:.0f})")
    else:
        print("  ℹ️  pain 未显著升高，无法判断言行一致性")


# ================================================================
# 测试五：多用户隔离
# ================================================================
def test_5_isolation():
    section("测试五：多用户隔离")
    uid_a = "bench_user_alpha"
    uid_b = "bench_user_beta"

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
        reply, _ = chat(inp, uid)
        record("isolation", i, uid, inp, reply, state_of(uid))
        print(f"  {i:02d}. [{uid[-5:]}] {inp[:30]:30s} -> {reply[:50]}")
        time.sleep(1)

    # 检查两个用户的状态是否独立
    st_a = state_of(uid_a)
    st_b = state_of(uid_b)
    print(f"\n  --- 隔离验证 ---")
    print(f"  alpha warmth: {st_a['warmth']:.3f}, events_count: {st_a['events_count']}")
    print(f"  beta  warmth: {st_b['warmth']:.3f}, events_count: {st_b['events_count']}")
    print(f"  alpha events: {st_a['recent_events'][:3]}")
    print(f"  beta  events: {st_b['recent_events'][:3]}")

    if abs(st_a['warmth'] - st_b['warmth']) > 0.01:
        print("  ✅ 两个用户warmth独立")
    else:
        print("  ⚠️ 报警: 两个用户warmth相同，可能状态未更新或隔离失败")

    if st_a['events_count'] > 0 and st_b['events_count'] > 0:
        a_events = st_a['recent_events']
        b_events = st_b['recent_events']
        overlap = set(a_events) & set(b_events)
        if not overlap:
            print("  ✅ events 独立无交叉")
        else:
            print(f"  ⚠️ 报警: events 交叉 {overlap}")


# ================================================================
# 输出报告
# ================================================================
def print_report():
    section("测试报告摘要")

    # 按测试分组
    groups = {}
    for r in RESULTS:
        t = r['test']
        if t not in groups:
            groups[t] = []
        groups[t].append(r)

    for test_name, items in groups.items():
        print(f"\n  {test_name}: {len(items)} 条记录")

    # 保存原始数据到 JSON
    out_path = "/mnt/data/catpaw/home/.meituan-catpaw/1079230951/desk_default_workspace/luo-shen-ai/benchmark_raw.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    print(f"\n  原始数据已保存: {out_path}")


import os

if __name__ == "__main__":
    print("=" * 60)
    print(" 洛神基准测试 — 测「是不是她自己」")
    print(f" 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" 目标: {BASE}")
    print("=" * 60)

    # 清空 benchmark 用户的旧状态（新建用户即自动干净）
    test_1_continuity()
    test_2_personality()
    test_3_memory()
    test_4_consistency()
    test_5_isolation()

    print_report()
    print("\n测试完成。")
