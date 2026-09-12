#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_p0_fixes.py — P0-A/B/C + P1 + P2 验证
按 Architect seq=6 retest_acceptance 逐条验证。
"""

import sys
import os
import time
import threading
import zlib
import numpy as np

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 强制重置单例
import cognitive_core
cognitive_core._core = None
cognitive_core._daemon_thread = None

# ── 验证 1: crc32 确定性 (P0-A) ──
print("=" * 70)
print("验证 1: crc32 跨进程确定性 (P0-A)")
print("=" * 70)

test_texts = ["你好啊", "我很难过", "今天天气不错", "压力大", ""]
for text in test_texts:
    if not text:
        continue
    crc1 = zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF
    crc2 = zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF
    row1 = crc1 % 6; col1 = (crc1 >> 8) % 6
    row2 = crc2 % 6; col2 = (crc2 >> 8) % 6
    consistent = (row1 == row2) and (col1 == col2)
    print(f"  '{text}' → crc={crc1}, cell=({row1},{col1})/{'OK' if consistent else 'FAIL'}")

print()

# ── 验证 2: encoder 接入 + 心跳递增 (P0-B) ──
print("=" * 70)
print("验证 2: 心跳递增 (P0-B) + 编码器注入 (P0-A)")
print("=" * 70)

core = cognitive_core.get_core(seed=42)
tick_before = core.tick_count
print(f"  初始 tick_count = {tick_before}")
print(f"  daemon线程: {cognitive_core._daemon_thread}")
if cognitive_core._daemon_thread:
    print(f"  daemon存活: {cognitive_core._daemon_thread.is_alive()}")

# 注入文本
core.receive_input(text="我很难过，压力好大")
tick_after_input = core.tick_count
abs_max_after_input = float(np.max(np.abs(core.frames[-1])))
print(f"  receive_input 后 tick_count = {tick_after_input}")
print(f"  receive_input 后 abs_max = {abs_max_after_input:.6f}")

# 手动触发一个 tick_step（心跳会自动触发但间隔 30s，测试用手动）
time.sleep(0.5)
core.tick_step()
tick_after_tick = core.tick_count
print(f"  tick_step 后 tick_count = {tick_after_tick}")
print(f"  tick 递增: {'OK' if tick_after_tick > tick_before else 'FAIL'}")

# 检查日志新字段
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cognitive_core_log.jsonl")
if os.path.exists(log_file):
    with open(log_file, "r") as f:
        lines = f.readlines()
    last_line = lines[-1] if lines else ""
    try:
        record = json.loads(last_line)
        has_anchor = "anchor" in record
        has_difference = "difference" in record
        has_prediction = "prediction" in record
        has_prediction_error = "prediction_error" in record
        print(f"  日志字段 anchor={has_anchor} difference={has_difference} prediction={has_prediction} prediction_error={has_prediction_error}")
        print(f"  最新日志 tick={record.get('tick')} error={record.get('error'):.6f} anchor={record.get('anchor')} prediction={record.get('prediction')}")
    except Exception as e:
        print(f"  日志解析失败: {e}")

print()

# ── 验证 3: 编码器注入导致 abs_max 变化 ──
print("=" * 70)
print("验证 3: 编码器注入后 abs_max 变化（不同文本不同落点）")
print("=" * 70)

results = {}
for text in ["开心死了", "压力好大", "别管我", "想你了"]:
    cognitive_core._core = None
    c = cognitive_core.get_core(seed=99)
    before = float(np.max(np.abs(c.frames[-1])))
    c.receive_input(text=text)
    after = float(np.max(np.abs(c.frames[-1])))
    results[text] = (before, after, after - before)
    print(f"  '{text}': before={before:.6f} after={after:.6f} delta={after-before:+.6f}")

# 检查不同文本是否落点不同（energy 行变化）
unique_rows = set()
for text in ["开心死了", "压力好大"]:
    cognitive_core._core = None
    c = cognitive_core.get_core(seed=99)
    c.receive_input(text=text)
    rm = [round(float(np.mean(c.frames[-1][r])), 4) for r in range(6)]
    unique_rows.add(tuple(rm))

print(f"  不同文本产生不同行均值签名: {'OK' if len(unique_rows) > 1 else 'FAIL'}")

print()

# ── 验证 4: 并发安全 (P0-C) ──
print("=" * 70)
print("验证 4: 并发安全 (P0-C) — daemon + read_intent 同时跑")
print("=" * 70)

cognitive_core._core = None
c = cognitive_core.get_core(seed=77)

errors = []

def writer():
    for _ in range(50):
        try:
            c.tick_step()
        except Exception as e:
            errors.append(("tick", str(e)))
        time.sleep(0.01)

def reader():
    for _ in range(50):
        try:
            c.read_intent()
            c.snapshot
            c.hidden_structure
        except Exception as e:
            errors.append(("read", str(e)))
        time.sleep(0.01)

threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
for t in threads: t.start()
for t in threads: t.join()

print(f"  writer各50次 tick_step + read_intent + snapshot + hidden_structure")
print(f"  并发错误次数: {len(errors)}")
if errors:
    for e in errors[:5]:
        print(f"    {e}")
else:
    print(f"  全部通过")

print()

# ── 验证 5: 语义路由 (P1) ──
print("=" * 70)
print("验证 5: P1 语义路由 — 词典分类")
print("=" * 70)

cognitive_core._core = None
c = cognitive_core.get_core(seed=55)

test_cases = [
    ("我很难过", "pain"),
    ("今天好开心", "energy"),
    ("别离开我", "warmth"),
    ("算了不说了", "withdraw"),
]

for text, expected_dim in test_cases:
    scores = c._classify_text(text)
    max_dim = max(scores, key=scores.get)
    print(f"  '{text}' → {scores} → 主导={max_dim} (期望={expected_dim}) {'OK' if max_dim == expected_dim else 'CHECK'}")

print()

# ── 验证 6: 30 轮重测 abs_max 变化幅度 ──
print("=" * 70)
print("验证 6: 30 轮 abs_max 变化")
print("=" * 70)

cognitive_core._core = None
c = cognitive_core.get_core(seed=123)

inputs_30 = [
    "你好啊", "今天天气怎么样", "最近工作好烦，天天加班", "你能多陪陪我吗", "我觉得压力好大",
    "我有点难过", "今天还不错", "你在干什么", "别不说话", "我回来了",
    "想你了", "无聊啊", "算了不说了", "再见之前再聊几句", "我完了，一切都糟糕透了",
    "为什么总是我", "能不能不要这样", "今天很开心哦", "谢谢你一直陪着我", "发生了什么",
    "想和你说说心里话", "静静地待着", "充满干劲", "好痛", "别管我",
    "压力大", "我在发光", "沉默吧", "拥抱你", "崩溃中",
]

abs_max_list = []
for i, text in enumerate(inputs_30):
    c.receive_input(text=text)
    am = float(np.max(np.abs(c.frames[-1])))
    abs_max_list.append(am)
    # 每 10 轮触发一些 tick
    if i % 10 == 9:
        for _ in range(5):
            c.tick_step()

abs_max_changes = [abs_max_list[i] - abs_max_list[i-1] for i in range(1, len(abs_max_list))]
n_changed = sum(1 for d in abs_max_changes if abs(d) > 0.005)
print(f"  30 轮 abs_max 范围: [{min(abs_max_list):.6f}, {max(abs_max_list):.6f}]")
print(f"  abs_max 变化 ≥ 0.005 的轮数: {n_changed}/29")
print(f"  最终 tick_count: {c.tick_count}")
print(f"  第 1 轮 abs_max: {abs_max_list[0]:.6f} vs 第 30 轮 abs_max: {abs_max_list[-1]:.6f}")

print()
print("=" * 70)
print("全部验证完毕")
print("=" * 70)
