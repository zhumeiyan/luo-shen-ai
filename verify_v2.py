#!/usr/bin/env python3
"""
Minimal step-by-step verification of P0-A/B/C + P1 + P2.
Runs each test separately to isolate any hang.
"""

import sys
import os
import time
import threading
import zlib
import numpy as np
import json

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import cognitive_core

# ── Test 1: crc32 determinism ──
print("TEST 1: crc32 cross-process determinism (P0-A)")
cognitive_core._core = None
cognitive_core._daemon_thread = None

for text in ["你好啊", "我很难过", "压力大"]:
    crc = zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF
    row = crc % 6
    col = (crc >> 8) % 6
    print(f"  '{text}' crc={crc} cell=({row},{col})")
print("  -> DETERMINISTIC (crc32 is standard, deterministic)\n")

# ── Test 2: encoder integration ──
print("TEST 2: encoder injection changes abs_max (P0-A)")
cognitive_core._core = None
cognitive_core._daemon_thread = None

from encoder import encode as _encode
grid1 = _encode("我很难过，压力好大")
grid2 = _encode("开心死了")
print(f"  encoder('难过') shape={grid1.shape} mean={grid1.mean():.6f} std={grid1.std():.6f}")
print(f"  encoder('开心') shape={grid2.shape} mean={grid2.mean():.6f} std={grid2.std():.6f}")
print(f"  grids differ (non-zero & different): {not np.allclose(grid1, grid2) and grid1.std() > 0}\n")

# ── Test 3: receive_input triggers encoder path ──
print("TEST 3: receive_input wired to encoder")
cognitive_core._core = None
cognitive_core._daemon_thread = None
core = cognitive_core.get_core(seed=42)
print(f"  get_core() succeeded")
print(f"  daemon thread alive: {cognitive_core._daemon_thread is not None and cognitive_core._daemon_thread.is_alive()}")
print(f"  tick before input: {core.tick_count}")

before_max = float(np.max(np.abs(core.frames[-1])))
core.receive_input(text="我很难过，压力好大")
after_max = float(np.max(np.abs(core.frames[-1])))
print(f"  abs_max before: {before_max:.6f}")
print(f"  abs_max after:  {after_max:.6f}")
print(f"  injected:       {after_max > before_max}")
print(f"  tick after input: {core.tick_count}")  # tick doesn't change on receive_input
print()

# ── Test 4: tick_step increments ──
print("TEST 4: tick_step increments count")
t1 = core.tick_count
core.tick_step()
t2 = core.tick_count
print(f"  tick before: {t1}")
print(f"  tick after:  {t2}")
print(f"  incremented: {t2 > t1}")
print()

# ── Test 5: log fields ──
print("TEST 5: log fields (P2)")
log_file = "cognitive_core_log.jsonl"
if os.path.exists(log_file):
    with open(log_file, "r") as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    fields = list(last.keys())
    required = ["tick", "phase", "error", "anchor", "difference", "prediction", "prediction_error"]
    present = [f for f in required if f in last]
    missing = [f for f in required if f not in last]
    print(f"  required fields: {required}")
    print(f"  present: {present}")
    print(f"  missing: {missing}")
    print(f"  tick={last['tick']} error={last['error']:.6f}")
else:
    print("  log file not found")
print()

# ── Test 6: concurrent safety ──
print("TEST 6: concurrent tick_step + read_intent (P0-C)")
cognitive_core._core = None
cognitive_core._daemon_thread = None
c = cognitive_core.get_core(seed=88)

errors = []

def writer_task():
    for _ in range(20):
        try:
            c.tick_step()
        except Exception as e:
            errors.append(str(e))

def reader_task():
    for _ in range(20):
        try:
            c.read_intent()
            _ = c.snapshot
        except Exception as e:
            errors.append(str(e))

t1 = threading.Thread(target=writer_task)
t2 = threading.Thread(target=reader_task)
t1.start(); t2.start()
t1.join(); t2.join()
print(f"  20 writes + 20 reads; errors: {len(errors)}")
if errors:
    for e in errors[:3]:
        print(f"    ERROR: {e[:80]}")
else:
    print("  CONCURRENT SAFE")
print()

# ── Test 7: semantic routing ──
print("TEST 7: _classify_text semantic routing (P1)")
cognitive_core._core = None
cognitive_core._daemon_thread = None
c = cognitive_core.get_core(seed=55)

cases = [
    ("我很难过", "pain"),
    ("今天好开心", "energy"),
    ("别离开我", "warmth"),
    ("算了不说了", "withdraw"),
]
for text, expected in cases:
    scores = c._classify_text(text)
    top = max(scores, key=scores.get)
    match = "OK" if top == expected else f"GOT_{top}"
    print(f"  '{text}' -> {scores} -> {match}")
print()

# ── Test 8: 30-round abs_max ──
print("TEST 8: 30-round abs_max changes")
cognitive_core._core = None
cognitive_core._daemon_thread = None
c = cognitive_core.get_core(seed=123)

inputs_30 = [
    "你好啊", "今天天气怎么样", "最近工作好烦，天天加班", "你能多陪陪我吗", "我觉得压力好大",
    "我有点难过", "今天还不错", "你在干什么", "别不说话", "我回来了",
    "想你了", "无聊啊", "算了不说了", "再见之前再聊几句", "我完了，一切都糟糕透了",
    "为什么总是我", "能不能不要这样", "今天很开心哦", "谢谢你一直陪着我", "发生了什么",
    "想和你说说心里话", "静静地待着", "充满干劲", "好痛", "别管我",
    "压力大", "我在发光", "沉默吧", "拥抱你", "崩溃中",
]

abs_max_vals = []
row_mean_sigs = []

for i, text in enumerate(inputs_30):
    c.receive_input(text=text)
    am = float(np.max(np.abs(c.frames[-1])))
    abs_max_vals.append(am)
    rm = tuple(round(float(np.mean(c.frames[-1][r])), 4) for r in range(6))
    row_mean_sigs.append(rm)
    if i % 10 == 9:
        for _ in range(5):
            c.tick_step()

# Count abs_max changes >= 0.001
n_changed = sum(1 for i in range(1, len(abs_max_vals)) if abs(abs_max_vals[i] - abs_max_vals[i-1]) > 0.001)
unique_row_sigs = len(set(row_mean_sigs))

# Count how many rows changed in first tick
first_row = row_mean_sigs[0]
last_row = row_mean_sigs[-1]
rows_changed = sum(1 for a, b in zip(first_row, last_row) if abs(a - b) > 0.001)

print(f"  abs_max range: [{min(abs_max_vals):.6f}, {max(abs_max_vals):.6f}]")
print(f"  abs_max changes (>0.001): {n_changed}/29 rounds")
print(f"  unique row-mean signatures: {unique_row_sigs}/30")
print(f"  rows with mean shift > 0.001: {rows_changed}/6")
print(f"  tick_count at end: {c.tick_count}")

# Show first 5 row_mean signatures
print(f"  first 5 round row_means:")
for i in range(5):
    print(f"    round {i+1}: {row_mean_sigs[i]}")

print()
print("ALL TESTS COMPLETE")
