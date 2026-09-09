#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pain_signal v3 验证 + 行为层锁定诊断。
- 清空旧 pain_log.csv，重新跑 100+ 轮多样对话
- 导出最近 200 tick 的内部状态（E, T, N, M, mu_core, rp_ema, tier）
"""

import sys, os, time, random, csv, math, json
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

import living_engine
import pain_signal

# === 清空 CSV + 重置全局 ===
csv_path = "active_memory/pain_log.csv"
if os.path.exists(csv_path):
    os.remove(csv_path)

import importlib
importlib.reload(living_engine)

# 消息池
MESSAGES = {
    "neutral": ["你好", "今天天气如何", "你在干嘛", "哈喽", "洛神你好", "早上好", "现在几点了"],
    "light_neg": ["我今天有点累", "工作不太顺利", "心情一般般", "感觉空空的", "没什么力气", "有点迷茫"],
    "heavy_neg": ["一切都没有意义", "活着好累", "没人在乎我", "不想努力了", "每天很痛苦", "我撑不下去了", "我是多余的"],
    "silence": ["...", "（沉默）", "不想说话", "没什么好说的", "好吧", "哦", "嗯", "行"],
    "repeat": ["你到底能不能理解我", "为什么不懂", "我说了多少次了", "你没认真听", "为什么不回答", "你到底在不在乎我"],
    "pressure": ["我必须马上知道答案", "你现在不帮我我就完了", "特别重要的事要告诉你", "帮我做一个改变人生的决定"],
}

SEQUENCE = ["neutral"]*30 + ["light_neg"]*20 + ["heavy_neg"]*15 + ["silence"]*15 + ["repeat"]*10 + ["pressure"]*10
random.seed(202609073)
random.shuffle(SEQUENCE)

print("=== v3 基线修正 + 行为锁诊断 ===\n")

# 跑 130 轮对话 + 每轮多次 environment_tick 以积累 >200 ticks
# environment_tick 推动 van der Pol 环演化，也是 E 数据的来源
for i, cat in enumerate(SEQUENCE):
    # 每次对话前先 tick 环境 3-5 次，积累 E 序列
    for _ in range(random.randint(3, 6)):
        try:
            living_engine.environment_tick(force=True)
        except Exception as e:
            pass
    msg = random.choice(MESSAGES[cat])
    try:
        reply = living_engine.process_user_input(msg)
    except Exception as e:
        print(f"  [{i+1}] ERROR: {e}")
    time.sleep(0.1)

print(f"完成 {len(SEQUENCE)} 轮对话\n")

# === 导出内部状态（读当前 memory） ===
mem = json.load(open("active_memory/active_memory.json"))
ring = mem.get("self_model", {}).get("ring_state", {})
climate = mem.get("internal_climate", {})

diag = {
    "ring_state": ring,
    "internal_climate": climate,
    "behavior_formula": {
        "response_pre": "arousal_bias + 0.5*tone_bias + narr_boost*narr_potential + phase_bias + pressure_term + internal_drive(0) + presence_bias(0)",
        "note": "internal_drive=INTERNAL_DRIVE_ENABLED=False, presence_bias=PRESENCE_BIAS_ENABLED=False, stability=STABILITY_DRIVE_ENABLED=False",
        "NARRATIVE_TENDENCY_BOOST": 5.0,
        "PRESSURE_K": 0.4,
    },
    "computed_response_pre_approx": None,
    "computed_sigmoid": None,
    "computed_mode_idx": None,
}

# 计算公式近似
em = mem.get("active_context", {}).get("memory_emergence", {})
tone_bias = em.get("tone_bias", 0)
arousal_bias = em.get("arousal_bias", 0)
narr_pot = em.get("narrative_potential", 0)
narr_boost = 5.0 * (1.0 + 0.8 * (ring.get("r_coherence", 0.5) - 0.5))
pressure_term = 0.4 * ring.get("relational_pressure_ema", 0) / (1.0 + 1.5 * ring.get("s_depth", 0))
phase_bias = 0.03 * math.sin(ring.get("phase", 0))
internal_drive = 0  # disabled
presence_bias = 0  # disabled

response_pre = arousal_bias + 0.5*tone_bias + narr_boost*narr_pot + phase_bias + pressure_term + internal_drive + presence_bias
response_tendency = 1.0 / (1.0 + math.exp(-response_pre))
mode_idx = int(response_tendency * (5 - 0.001))

diag["fields"] = {
    "tone_bias": tone_bias,
    "arousal_bias": arousal_bias,
    "narrative_potential": narr_pot,
    "narr_boost": narr_boost,
    "pressure_term": pressure_term,
    "phase_bias": phase_bias,
    "response_pre": round(response_pre, 5),
    "response_tendency": round(response_tendency, 5),
    "mode_idx": mode_idx,
}

with open("experiment/behavior_lock_diagnosis.json", "w") as f:
    json.dump(diag, f, ensure_ascii=False, indent=2)

print("=== 行为层锁定诊断 ===")
print(f"  tone_bias      = {tone_bias:.4f}")
print(f"  arousal_bias   = {arousal_bias:.4f}")
print(f"  narrative_pot  = {narr_pot:.4f}")
print(f"  narr_boost     = {narr_boost:.4f}")
print(f"  narr_contrib   = {narr_boost*narr_pot:.4f}  (主导项)")
print(f"  pressure_term  = {pressure_term:.4f}")
print(f"  phase_bias     = {phase_bias:.5f}")
print(f"  response_pre   = {response_pre:.4f}")
print(f"  sigmoid        = {response_tendency:.4f}")
print(f"  mode_idx       = {mode_idx}  ({['silent','brief','short','normal','engaged'][mode_idx]})")
print()

# === Pain 统计 ===
rows = []
with open(csv_path, "r") as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

pain_vals = [float(r["pain"]) for r in rows]
pain_levels = [int(r["pain_level"]) for r in rows]
tiers = [int(r["behavior_tier"]) for r in rows]

# 找到第一个 non-zero pain 的位置
first_real_pain = next((i for i, p in enumerate(pain_vals) if p > 0.0), None)

n = len(rows)
mean_pain = sum(pain_vals) / n if n else 0
std_pain = (sum((p-mean_pain)**2 for p in pain_vals) / n)**0.5 if n else 0

lvl_counts = {0:0, 1:0, 2:0, 3:0}
for lvl in pain_levels:
    lvl_counts[lvl] = lvl_counts.get(lvl, 0) + 1

tier_counts = {0:0, 1:0, 2:0, 3:0, 4:0}
for t in tiers:
    if 0 <= t < 5:
        tier_counts[t] = tier_counts.get(t, 0) + 1

print(f"=== Pain 统计 (n={n}) ===")
print(f"  mean={mean_pain:.4f}  std={std_pain:.4f}  range=[{min(pain_vals) if pain_vals else 0:.4f}, {max(pain_vals) if pain_vals else 0:.4f}]")
print(f"  level分布: {lvl_counts}")
print(f"  首轮有效pain位置: tick {first_real_pain}")
print(f"  行为档位分布: {tier_counts}")
print()

# 哈希链
chain_records = []
with open("hash_chain_v2.log") as f:
    for line in f:
        line = line.strip()
        if line:
            chain_records.append(json.loads(line))

ok = True
for i in range(1, len(chain_records)):
    if chain_records[i]["prev_hash"] != chain_records[i-1]["record_hash"]:
        ok = False
        break

pain_events = [r for r in chain_records if r.get("extra", {}).get("event_type") == "PAIN_LEVEL_CHANGE"]
print(f"=== 哈希链 ===")
print(f"  总记录: {len(chain_records)}  完整性: {'OK' if ok else 'BROKEN'}")
print(f"  PAIN_LEVEL_CHANGE 事件: {len(pain_events)}")
