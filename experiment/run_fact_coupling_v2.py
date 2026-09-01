#!/usr/bin/env python3
"""
实验 v2：事实耦合——F 进入内部状态的更精确检测

方法：
1. 先稳定环到周期状态（先跑 500 tick 让冷启动 S 小步上升）
2. A 路径：再跑 100 tick 同时把 F 设为恒值（模拟已存在事实）
3. B 路径：同上但 F = 0
4. 比较 100 tick 内的平均 / 标准差，看 M 和 mu_eff 的偏移
5. 不上 LLM，只看内部状态
"""

import os, sys, shutil, json, math

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, BASE)

import living_engine
from fact_extractor import extract_and_save
import importlib; importlib.reload(living_engine)

SRC = os.path.join(BASE, "active_memory", "active_memory.json.experiment_neutral")
DST = os.path.join(BASE, "active_memory", "active_memory.json")

STABILIZE = 500
OBSERVE = 600

def run_stabilize(mem, n):
    for i in range(n):
        env = {"light": 0.5, "noise": 0.0, "temperature": 0.5}
        living_engine._update_luoshen_coupled(mem, env, tick_id=i)

def tick_with_fact(mem, tick_id):
    env = {"light": 0.5, "noise": 0.0, "temperature": 0.5}
    living_engine._update_luoshen_coupled(mem, env, tick_id=tick_id)

# ── A 路径：写入 5 条事实 → F ≈ 0.848 ──
shutil.copy2(SRC, DST)
mem_a = living_engine._load_json(DST)
for s in ["我下个月要离开这座城市了", "我其实很怕一个人待着", "我不爱吃甜的东西"]:
    _, mem_a = extract_and_save(s, mem_a)
run_stabilize(mem_a, STABILIZE)

trace_a_F = []
trace_a_S = []
trace_a_M = []
trace_a_mu = []
for i in range(OBSERVE):
    tick_with_fact(mem_a, tick_id=STABILIZE + i)
    rs = mem_a["self_model"]["ring_state"]
    ic = mem_a["internal_climate"]
    trace_a_F.append(rs.get("F", 0))
    trace_a_S.append(rs.get("S", 0))
    trace_a_M.append(ic["memory_pressure"])
    trace_a_mu.append(rs.get("mu_eff", 0))

# ── B 路径：无事实 → F = 0 ──
shutil.copy2(SRC, DST)
mem_b = living_engine._load_json(DST)
run_stabilize(mem_b, STABILIZE)

trace_b_S = []
trace_b_M = []
trace_b_mu = []
for i in range(OBSERVE):
    tick_with_fact(mem_b, tick_id=STABILIZE + i)
    rs = mem_b["self_model"]["ring_state"]
    ic = mem_b["internal_climate"]
    trace_b_S.append(rs.get("S", 0))
    trace_b_M.append(ic["memory_pressure"])
    trace_b_mu.append(rs.get("mu_eff", 0))

def stats(vals):
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean)**2 for x in vals) / n
    std = math.sqrt(var)
    return mean, std

avg_F, std_F = stats(trace_a_F)
avg_Sa, std_Sa = stats(trace_a_S)
avg_Sb, std_Sb = stats(trace_b_S)
avg_Ma, std_Ma = stats(trace_a_M)
avg_Mb, std_Mb = stats(trace_b_M)
avg_muA, std_muA = stats(trace_a_mu)
avg_muB, std_muB = stats(trace_b_mu)

print("=" * 60)
print(f"事实耦合实验（STABILIZE={STABILIZE}, OBSERVE={OBSERVE}）")
print("=" * 60)
print(f"{'指标':<12} {'A (F≈0.85)':>18} {'B (F=0)':>18} {'Δ(mean)':>12}")
print("-" * 60)
print(f"{'F':<12} {avg_F:>9.5f}±{std_F:<7.5f} {'0.00000':>18} {avg_F:>+12.5f}")
print(f"{'S':<12} {avg_Sa:>9.5f}±{std_Sa:<7.5f} {avg_Sb:>9.5f}±{std_Sb:<7.5f} {avg_Sa-avg_Sb:>+12.6f}")
print(f"{'M':<12} {avg_Ma:>9.5f}±{std_Ma:<7.5f} {avg_Mb:>9.5f}±{std_Mb:<7.5f} {avg_Ma-avg_Mb:>+12.6f}")
print(f"{'mu_eff':<12} {avg_muA:>9.5f}±{std_muA:<7.5f} {avg_muB:>9.5f}±{std_muB:<7.5f} {avg_muA-avg_muB:>+12.6f}")

print()
print("=" * 60)
print("最终回复 Demo（仅展示，非实验结论）")
print("=" * 60)
living_engine._save_json_atomic(DST, mem_a)
res_a = living_engine.generate_response("在吗？")
living_engine._save_json_atomic(DST, mem_b)
res_b = living_engine.generate_response("在吗？")
print(f"A: {res_a['reply'][:120]}")
print(f"B: {res_b['reply'][:120]}")
print(f"回复不同: {res_a.get('reply','') != res_b.get('reply','')}")
