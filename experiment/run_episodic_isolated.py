#!/usr/bin/env python3
"""
分离测试：确认回复差异来自内部状态还是已知事实上下文

步骤：
1. A / B 分别编码不同的情景记忆残影
2. 跑 N tick 让内部状态分化
3. 清空所有 known_facts（消除文本注入）
4. 对两者输入"在吗？"——此时 LLM 看不到任何事实文本
5. 观察回复是否仍有差异（如果仍有差异，来自内部状态；如果无差异，原差异由文本注入导致）

对比：
- 保留 known_facts 的原始测试
- 清零 known_facts 后的测试
"""
import os, sys, shutil
sys.path.insert(0, '..')
import importlib

import living_engine
importlib.reload(living_engine)

SRC = 'active_memory/active_memory.json.experiment_neutral'
DST = 'active_memory/active_memory.json'
TICKS = 8000
SAVE_EVERY = 800

def run_internal_ticks(mem, n, label=""):
    trace = []
    for i in range(n):
        env = {"light": 0.5, "noise": 0.0, "temperature": 0.5}
        living_engine._update_luoshen_coupled(mem, env, tick_id=i)
        if i % SAVE_EVERY == 0 or i == n - 1:
            rs = mem.get('self_model', {}).get('ring_state', {})
            ic = mem.get('internal_climate', {})
            trace.append({
                "tick": i,
                "E": ic.get("emotion_intensity"), "T": ic.get("tension"),
                "N": ic.get("energy"), "M": ic.get("memory_pressure"),
                "S": rs.get("S"), "mu_eff": rs.get("mu_eff"),
                "F_mem": rs.get("F_mem", 0), "n_mem": len(mem.get('user_model',{}).get('episodic_memory',[])),
            })
    return trace

def fresh_mem():
    shutil.copy2(SRC, DST)
    m = living_engine._load_json(DST)
    m.get('user_model', {}).setdefault('episodic_memory', [])
    living_engine._save_json_atomic(DST, m)
    return living_engine._load_json(DST)

# ── A：情绪残影 ──
mem_a = fresh_mem()
for _ in range(3):
    mem_a["internal_climate"]["emotion_intensity"] = -0.8
    mem_a["internal_climate"]["tension"] = 1.2
    mem_a["internal_climate"]["energy"] = 0.3
    living_engine._encode_episodic_memory(mem_a)
living_engine._save_json_atomic(DST, mem_a)
run_internal_ticks(mem_a, TICKS, "A")

# ── B：平静残影 ──
mem_b = fresh_mem()
for _ in range(3):
    mem_b["internal_climate"]["emotion_intensity"] = 0.1
    mem_b["internal_climate"]["tension"] = 0.1
    mem_b["internal_climate"]["energy"] = 0.5
    living_engine._encode_episodic_memory(mem_b)
living_engine._save_json_atomic(DST, mem_b)
run_internal_ticks(mem_b, TICKS, "B")

# ── 读取最终状态 ──
rs_a = mem_a.get("self_model", {}).get("ring_state", {})
rs_b = mem_b.get("self_model", {}).get("ring_state", {})
ic_a = mem_a.get("internal_climate", {})
ic_b = mem_b.get("internal_climate", {})

print("=" * 60)
print(f"最终状态（{TICKS} ticks 后，无 LLM 介入）")
print("=" * 60)
print(f"{'指标':<10} {'A(情绪)':>12} {'B(平静)':>12} {'Δ(A-B)':>12}")
for key, ka, kb in [
    ("E", "emotion_intensity", "emotion_intensity"),
    ("T", "tension", "tension"),
    ("N", "energy", "energy"),
    ("M", "memory_pressure", "memory_pressure"),
]:
    va = ic_a.get(ka, 0); vb = ic_b.get(kb, 0)
    print(f"{key:<10} {va:>12.4f} {vb:>12.4f} {va-vb:>+12.5f}")
for key in ["S", "mu_eff", "F_mem"]:
    va = rs_a.get(key, 0); vb = rs_b.get(key, 0)
    print(f"{key:<10} {va:>12.4f} {vb:>12.4f} {va-vb:>+12.6f}")

print(f"\nA 记忆点数: {len(mem_a.get('user_model',{}).get('episodic_memory',[]))}")
print(f"B 记忆点数: {len(mem_b.get('user_model',{}).get('episodic_memory',[]))}")

# ── 第一轮：保留 known_facts（原始测试）──
print("\n" + "=" * 60)
print("第一轮：保留 known_facts")
print("=" * 60)
living_engine._save_json_atomic(DST, mem_a)
res_a1 = living_engine.generate_response("在吗？")
living_engine._save_json_atomic(DST, mem_b)
res_b1 = living_engine.generate_response("在吗？")
print(f"A: {res_a1.get('reply','')[:150]}  llm={res_a1.get('llm_called')}")
print(f"B: {res_b1.get('reply','')[:150]}  llm={res_b1.get('llm_called')}")
print(f"差异: {res_a1.get('reply','') != res_b1.get('reply','')}")

# ── 第二轮：清零 known_facts（隔离记忆引力效应）──
mem_a2 = fresh_mem()
mem_a2["internal_climate"]["emotion_intensity"] = -0.8
mem_a2["internal_climate"]["tension"] = 1.2
mem_a2["internal_climate"]["energy"] = 0.3
for _ in range(3):
    living_engine._encode_episodic_memory(mem_a2)
living_engine._save_json_atomic(DST, mem_a2)
run_internal_ticks(mem_a2, TICKS, "A2")

mem_b2 = fresh_mem()
mem_b2["internal_climate"]["emotion_intensity"] = 0.1
mem_b2["internal_climate"]["tension"] = 0.1
mem_b2["internal_climate"]["energy"] = 0.5
for _ in range(3):
    living_engine._encode_episodic_memory(mem_b2)
living_engine._save_json_atomic(DST, mem_b2)
run_internal_ticks(mem_b2, TICKS, "B2")

# 清零所有已知事实
mem_a2["user_model"]["known_facts"] = {}
mem_b2["user_model"]["known_facts"] = {}
living_engine._save_json_atomic(DST, mem_a2)
living_engine._save_json_atomic(DST, mem_b2)

print("\n" + "=" * 60)
print("第二轮：清空 known_facts 后")
print("=" * 60)
print(f"清零后 A 记忆点数: {len(mem_a2.get('user_model',{}).get('episodic_memory',[]))}")
print(f"清零后 B 记忆点数: {len(mem_b2.get('user_model',{}).get('episodic_memory',[]))}")

living_engine._save_json_atomic(DST, mem_a2)
res_a2 = living_engine.generate_response("在吗？")
living_engine._save_json_atomic(DST, mem_b2)
res_b2 = living_engine.generate_response("在吗？")
print(f"A: {res_a2.get('reply','')[:150]}  llm={res_a2.get('llm_called')}")
print(f"B: {res_b2.get('reply','')[:150]}  llm={res_b2.get('llm_called')}")
print(f"差异: {res_a2.get('reply','') != res_b2.get('reply','')}")

print("\n" + "=" * 60)
print("诚实结论")
print("=" * 60)
print(f"内部状态 ΔE = {ic_a.get('emotion_intension',ic_a.get('emotion_intensity',0)) - ic_b.get('emotion_intension',ic_b.get('emotion_intensity',0)):+.4f}")
print(f"内部状态 ΔM = {ic_a.get('memory_pressure',0) - ic_b.get('memory_pressure',0):+.4f}")
print(f"已知事实注入下回复不同: {res_a1.get('reply','') != res_b1.get('reply','')}")
print(f"清空已知事实后回复不同: {res_a2.get('reply','') != res_b2.get('reply','')}")
