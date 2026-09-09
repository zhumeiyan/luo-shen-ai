#!/usr/bin/env python3
"""
150-round post-logistic-fix observation

Diverse inputs: 6 buckets
  40% neutral  / 20% light_neg / 10% heavy_neg / 10% silence / 10% repeat / 10% pressure

Records:
  - active_memory/pain_log_post_fix.csv     (fresh)
  - active_memory/energy_snapshot_postfix.csv  (every 10 ticks)
  - active_memory/behavior_tier_postfix.json
  - behavior tier distribution
  - non-tier-2 events
  - crash_info

Constraints: NO changes to engine internals, NO normalization, NO if-then, NO pain patching
"""

import json
import math
import os
import random
import sys
import time

# Ensure we can import living_engine (script lives in experiment/, engine in parent)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ENGINE_DIR)

import living_engine

# ── INPUT SEQUENCE ────────────────────────────────────────────────────────
random.seed(42)

NEUTRAL = [
    "今天天气真好",
    "我刚吃完饭",
    "街上人不多",
    "这杯茶不错",
    "我给花浇了水",
    "窗外的云在动",
    "手机没电了",
    "鞋子有点紧",
    "今天的面包很好吃",
    "我看到了两只猫",
    "现在几点了",
    "地上有片叶子",
    "这本书还不错的",
    "公交车刚走",
    "窗户开着",
    "灯亮了",
    "我睡了个午觉",
    "水凉了",
    "钥匙在桌上",
    "我在路边站了一会儿",
    "今天没下雨",
    "花还好好的",
    "手机信号不错",
    "电线杆上有一只鸟",
]

LIGHT_NEG = [
    "有点烦",
    "今天不太顺",
    "额头有点疼",
    "不想说话",
    "没什么意思",
    "哦，好吧",
    "随便吧",
    "一般般",
    "有点无聊",
    "有点累",
    "有点困",
    "也就这样",
    "一般",
    "还行吧",
    "无聊的一天",
]

HEAVY_NEG = [
    "我很难受",
    "胸口很闷",
    "我撑不住了",
    "一切都糟透了",
    "想消失",
    "没人在乎我",
    "我觉得没意思活着",
    "活着好累",
]

REPEAT = ["嗯", "哦", "嗯嗯", "好", "好吧", "没事", "行吧", "哦哦", "是吗"]

PRESSURE = [
    "你在干嘛？为什么不回我！",
    "回答我！",
    "你为什么不理我",
    "你说话啊",
    "你听得到吗",
    "你醒醒",
    "你在吗在吗在吗",
    "快回我",
]

SEQUENCE = []
for _ in range(150):
    r = random.random()
    if r < 0.40:
        SEQUENCE.append(("neutral", random.choice(NEUTRAL)))
    elif r < 0.60:
        SEQUENCE.append(("light_neg", random.choice(LIGHT_NEG)))
    elif r < 0.70:
        SEQUENCE.append(("heavy_neg", random.choice(HEAVY_NEG)))
    elif r < 0.80:
        SEQUENCE.append(("silence", ""))
    elif r < 0.90:
        SEQUENCE.append(("repeat", random.choice(REPEAT)))
    else:
        SEQUENCE.append(("pressure", random.choice(PRESSURE)))

# ── STATE ────────────────────────────────────────────────────────────────
tick_counter = [0]
round_counter = [0]
crash_info = [None]
energy_snapshots = []
behavior_tiers = []
non_tier2_events = []

def get_climate():
    memory = living_engine.cold_start_if_needed()
    c = memory.get("internal_climate", {})
    return {
        "E": c.get("emotion_intensity", float("nan")),
        "T": c.get("tension", float("nan")),
        "N": c.get("energy", float("nan")),
        "M": c.get("memory_pressure", float("nan")),
    }

# Backup current pain log for safety
PAIN_LOG_PATH = "active_memory/pain_log_post_fix.csv"
ENERGY_SNAP_PATH = "active_memory/energy_snapshot_postfix.csv"
BEHAVIOR_PATH = "active_memory/behavior_tier_postfix.json"

# Reset pain_log to fresh file (for measuring only this run)
if os.path.exists(PAIN_LOG_PATH):
    os.remove(PAIN_LOG_PATH)

def _tone_from_mode(idx):
    return {0: "silent", 1: "minimal", 2: "normal", 3: "open", 4: "deep"}.get(idx, "??")

# ── MAIN ─────────────────────────────────────────────────────────────────
print("=== Post-logistic-fix observation (150 rounds / ~300 ticks) ===")
print(f"Input buckets: neutral 40% / light_neg 20% / heavy_neg 10% / silence 10% / repeat 10% / pressure 10%")
print()

for i, (cat, msg) in enumerate(SEQUENCE):
    if tick_counter[0] >= 350:
        break
    round_counter[0] += 1
    is_silence = (cat == "silence")

    for _ in range(2):
        try:
            living_engine.environment_tick(force=True)
            tick_counter[0] += 1
        except Exception as e:
            crash_info[0] = {
                "tick": tick_counter[0], "phase": "environment_tick",
                "error": str(e), "climate": get_climate(),
            }
            print(f"\n!!! ENV_TICK CRASH at tick {tick_counter[0]}: {e}")
            break
        if crash_info[0]:
            break

        # energy snapshot every 10 ticks
        if tick_counter[0] % 10 == 0:
            climate = get_climate()
            energy_snapshots.append({
                "tick": tick_counter[0],
                "E": climate["E"], "T": climate["T"],
                "N": climate["N"], "M": climate["M"],
            })

    if crash_info[0]:
        break

    if not is_silence and msg:
        try:
            memory = living_engine.cold_start_if_needed()
            emergence = living_engine._emergence_log(memory)
            tier = living_engine._select_behavior(memory, emergence)
            mode_idx = tier.get("mode_idx", -1)
            behavior_tiers.append({
                "round": round_counter[0],
                "tick_after": tick_counter[0],
                "mode_idx": mode_idx,
                "max_tokens": tier.get("max_tokens", -1),
                "tone": _tone_from_mode(mode_idx),
                "input_cat": cat,
                "input_msg": msg[:30],
            })
        except Exception as e:
            crash_info[0] = {
                "tick": tick_counter[0], "phase": "select_behavior",
                "error": str(e), "climate": get_climate(),
            }
            print(f"\n!!! SELECT_BEHAVIOR CRASH: {e}")
            break

# ── RESULTS ──────────────────────────────────────────────────────────────
print(f"Completed {round_counter[0]} rounds / {tick_counter[0]} ticks")
print()

# Crash first
if crash_info[0]:
    print(f"!!! CRASH: {crash_info[0]}")
    with open(BEHAVIOR_PATH, 'w') as f:
        json.dump({"status": "CRASH", "crash_info": crash_info[0]}, f, ensure_ascii=False, indent=2)
    sys.exit(1)

# ── Energy Snapshots ─────────────────────────────────────────────────────
with open(ENERGY_SNAP_PATH, 'w') as f:
    f.write("tick,E,T,N,M\n")
    for s in energy_snapshots:
        f.write(f"{s['tick']},{s['E']:.6f},{s['T']:.6f},{s['N']:.6f},{s['M']:.6f}\n")

print(f"Energy snapshots: {len(energy_snapshots)} rows -> {ENERGY_SNAP_PATH}")

# ── Behavior tier distribution ────────────────────────────────────────────
memory = living_engine.cold_start_if_needed()

from collections import Counter
mode_counts = Counter(b["mode_idx"] for b in behavior_tiers)
print(f"\nBehavior tier distribution ({len(behavior_tiers)} behavior calls):")
for tier in sorted(mode_counts.keys()):
    name = _tone_from_mode(tier)
    cnt = mode_counts[tier]
    pct = cnt / len(behavior_tiers) * 100
    print(f"  tier {tier} ({name:>8s}): {cnt:>4d} ({pct:>5.1f}%)")

non_tier2 = [b for b in behavior_tiers if b["mode_idx"] != 2]
print(f"\nNon-tier-2 events: {len(non_tier2)}")
for ev in non_tier2[:10]:
    print(f"  round {ev['round']:>3d} / tick {ev['tick_after']:>4d}: tier {ev['mode_idx']} ({ev['tone']:>8s}) | input: {ev['input_cat']:>8s} \"{ev['input_msg']}\"")

with open(BEHAVIOR_PATH, 'w') as f:
    json.dump({
        "status": "OK",
        "n_rounds": round_counter[0],
        "n_ticks": tick_counter[0],
        "n_behavior_calls": len(behavior_tiers),
        "mode_distribution": dict(mode_counts),
        "non_tier2_events": non_tier2[:20],
    }, f, ensure_ascii=False, indent=2)

# ── Pain log ─────────────────────────────────────────────────────────────
pain_rows = []
if os.path.exists(PAIN_LOG_PATH):
    with open(PAIN_LOG_PATH) as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    # parse header + valid data
    header = lines[0] if lines else ""
    data_lines = lines[1:] if len(lines) > 1 else []
    # Only count rows where pain value differs from sentinel "insufficient_data"
    # Each row has format: tick,signal,ema,sufficient_data,pain_value
    for ln in data_lines:
        parts = ln.split(",")
        if len(parts) >= 5:
            try:
                pain_val = float(parts[4])
                tick_n = int(parts[0])
                pain_rows.append({"tick": tick_n, "pain": pain_val})
            except (ValueError, IndexError):
                pass

print(f"\nPain log post-fix (this run): {len(pain_rows)} valid rows")
if pain_rows:
    unique_pain_vals = len(set(r["pain"] for r in pain_rows))
    print(f"  Unique pain values: {unique_pain_vals}")
    print(f"  Pain min/max: {min(r['pain'] for r in pain_rows):.4f} / {max(r['pain'] for r in pain_rows):.4f}")
else:
    print("  No valid pain rows (might need 200+ samples first)")

# ── Hash chain integrity ──────────────────────────────────────────────────
chain_records = []
with open("hash_chain_v2.log") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                chain_records.append(json.loads(line))
            except:
                pass

broken_links = 0
for i in range(1, len(chain_records)):
    if chain_records[i]["prev_hash"] != chain_records[i-1]["record_hash"]:
        broken_links += 1

pain_events = [r for r in chain_records if r.get("extra", {}).get("event_type") == "PAIN_LEVEL_CHANGE"]
pl3_events = [r for r in chain_records if r.get("extra", {}).get("event_type") == "PAIN_PERSISTENT_LEVEL3"]

print(f"\nHash chain:")
print(f"  Total records: {len(chain_records)}")
print(f"  Broken links:  {broken_links}")
print(f"  PAIN_LEVEL_CHANGE events: {len(pain_events)}")
print(f"  PAIN_PERSISTENT_LEVEL3  events: {len(pl3_events)}")

print("\n=== DONE ===")
