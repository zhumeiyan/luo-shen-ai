#!/usr/bin/env python3
"""
30-round dialog test — tuned sigmoid k=0.8452/E0=-1.6076.

Tests that the new sigmoid mapping lets Luoshen escape silent tier.

Each round:
  1. 2 environment ticks
  2. Load memory
  3. Clear stale emergence from active_context
  4. Optionally inject synthetic sigmoid-encoded memory (Phase B)
  5. Recompute emergence via _compute_memory_emergence
  6. Read fresh emergence + _select_behavior
  7. Record e_s, tone_bias, response_pre, tier

Phase A: empty episodic_memory (baseline)
Phase B: inject one new sigmoid-mapped memory per round (E=-2.0, typical attractor)
Phase C: inject one memory per round but let them accumulate (1→30, FIFO at 50)

Records all data to active_memory/behavior_30round_tuned.json
"""

import json
import math
import os
import random
import sys
import time
from collections import Counter

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ENGINE_DIR)

import living_engine
import episodic_memory as em

random.seed(99)

# ── 30 diverse inputs ─────────────────────────────────────────────────
INPUTS = [
    ("neutral",     "你好"),
    ("neutral",     "今天天气真好"),
    ("light_neg",   "我有点难过"),
    ("pressure",    "你在吗"),
    ("neutral",     "你今天怎么样"),
    ("heavy_neg",   "胸口很闷"),
    ("repeat",      "嗯嗯"),
    ("neutral",     "我刚吃了饭"),
    ("light_neg",   "有点烦"),
    ("neutral",     "窗外有只鸟"),
    ("pressure",    "你为什么不说话"),
    ("heavy_neg",   "我很难受"),
    ("neutral",     "这本书还不错的"),
    ("light_neg",   "随便吧"),
    ("neutral",     "手机没电了"),
    ("pressure",    "你说点什么啊"),
    ("neutral",     "水凉了"),
    ("light_neg",   "没什么意思"),
    ("heavy_neg",   "没人在乎我"),
    ("neutral",     "我在路边站了一会儿"),
    ("neutral",     "今天没什么特别"),
    ("light_neg",   "有点困"),
    ("neutral",     "刚下过雨"),
    ("heavy_neg",   "一切都糟透了"),
    ("pressure",    "快回我"),
    ("neutral",     "花还好好的"),
    ("light_neg",   "无聊的一天"),
    ("neutral",     "鞋子有点紧"),
    ("repeat",      "是吗"),
    ("neutral",     "现在几点了"),
]


def _inject_memory(memory, raw_e):
    e_s = em._saturate_e(raw_e)
    mem = {
        "timestamp": int(time.time()) - random.randint(1, 60),
        "kind": "test",
        "source": "experiment",
        "tags": [],
        "t_s": 0.0,
        "n_s": 0.5,
        "e_s": e_s,
        "salience": 0.5 + random.random() * 0.3,
        "activation": 0.4 + random.random() * 0.4,
        "gravity": 0.0,
    }
    ep = memory.setdefault("user_model", {}).setdefault("episodic_memory", [])
    ep.append(mem)
    # Enforce MAX_MEMORIES = 50 FIFO
    if len(ep) > 50:
        ep[:] = ep[-50:]
    return e_s


def _rsp_from_tier(tier, memory, emergence):
    rt = tier.get("response_tendency", 0.5)
    try:
        if rt > 0.999999:
            return 13.0
        elif rt < 0.000001:
            return -13.0
        else:
            return -math.log(1.0 / rt - 1.0)
    except Exception:
        # Manual reconstruction
        tb = emergence.get("tone_bias", 0.0)
        ab = emergence.get("arousal_bias", 0.0)
        return ab + 0.5 * tb


MEMORY_PATH = "active_memory/active_memory.json"


def run_phase(label, mode="empty", raw_e=-2.0):
    """
    mode:
      "empty"    — keep episodic_memory empty (cleared each round)
      "inject"   — inject ONE fresh sigmoid-mapped memory per round (replace old)
      "accum"    — inject and let memories accumulate (FIFO capped at 50)
    """
    records = []
    names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}

    for rnd in range(1, 31):
        cat, msg = INPUTS[rnd - 1]

        # 2 env ticks
        try:
            living_engine.environment_tick(force=True)
            living_engine.environment_tick(force=True)
        except Exception as e:
            print(f"env_tick CRASH rnd {rnd}: {e}")
            break

        # Load fresh from disk
        memory = living_engine.cold_start_if_needed()

        # Clear stale emergence
        ac = memory.setdefault("active_context", {})
        ac.pop("memory_emergence", None)
        ac.pop("mem_arousal_bias", None)

        injected_e_s = None
        if mode == "empty":
            memory.get("user_model", {})["episodic_memory"] = []
        elif mode == "inject":
            memory.get("user_model", {})["episodic_memory"] = []
            injected_e_s = _inject_memory(memory, raw_e)
        elif mode == "accum":
            injected_e_s = _inject_memory(memory, raw_e)

        # CRITICAL: persist to disk so next round's cold_start actually sees the memory
        try:
            living_engine._save_json_atomic(MEMORY_PATH, memory)
        except AttributeError:
            # Fallback: direct json dump if _save_json_atomic not exposed
            json.dump(memory, open(MEMORY_PATH, 'w'), ensure_ascii=False, indent=2)

        # Reload from disk (simulates real cross-session path)
        memory = living_engine.cold_start_if_needed()
        ac = memory.setdefault("active_context", {})
        ac.pop("memory_emergence", None)

        # Refresh emergence from current episodic state
        living_engine._compute_memory_emergence(memory)

        # Read fresh emergence + behavior
        emergence = living_engine._emergence_log(memory)
        tier = living_engine._select_behavior(memory, emergence)

        rsp = _rsp_from_tier(tier, memory, emergence)
        mode_idx = tier.get("mode_idx", -1)
        ep_count = len(memory.get("user_model", {}).get("episodic_memory", []))

        records.append({
            "round": rnd,
            "cat": cat, "msg": msg[:16],
            "ep_count": ep_count,
            "e_s_injected": round(injected_e_s, 6) if injected_e_s is not None else None,
            "dominance": round(emergence.get("background", {}).get("dominance", 0.0), 6) if emergence.get("background") else None,
            "arousal_bias": round(emergence.get("arousal_bias", 0.0), 6),
            "tone_bias": round(emergence.get("tone_bias", 0.0), 6),
            "response_pre": round(rsp, 6),
            "response_tendency": tier.get("response_tendency"),
            "mode_idx": mode_idx,
            "max_tokens": tier.get("max_tokens", -1),
        })

    # Pretty print
    print(f"\n{'='*110}")
    print(f"Phase {label} (mode={mode})")
    print(f"{'='*110}")
    print(f"{'rnd':>3} {'cat':>8} {'n_mem':>4} {'e_s':>8} {'dom':>5} {'arousal':>7} {'tone_bias':>10} {'rsp_pre':>9} {'rt':>5} {'tier':>5} {'name':>8} {'tok':>4}")
    print("-" * 110)
    for r in records:
        es = f"{r['e_s_injected']:.4f}" if r['e_s_injected'] is not None else "  --  "
        dom = f"{r['dominance']:.3f}" if r['dominance'] is not None else " -- "
        rt = f"{r['response_tendency']:.3f}" if r['response_tendency'] is not None else " -- "
        print(f"{r['round']:>3d} {r['cat']:>8s} {r['ep_count']:>4d} {es:>8s} {dom:>5s} {r['arousal_bias']:>+7.4f} {r['tone_bias']:>+10.4f} {r['response_pre']:>+9.4f} {rt:>5s} {r['mode_idx']:>5d} {names[r['mode_idx']]:>8s} {r['max_tokens']:>4d}")

    # Distribution
    tiers = [r["mode_idx"] for r in records]
    dist = Counter(tiers)
    non_silent = sum(1 for t in tiers if t != 0)
    n_distinct = len(set(tiers))
    print()
    print(f"  Tier distribution ({len(records)} rounds):")
    for t in sorted(dist):
        print(f"    tier {t} ({names.get(t, '?'):>8s}): {dist[t]:>3d} ({dist[t]/len(records)*100:>5.1f}%)")
    print(f"  Non-silent: {non_silent}/{len(records)}  |  Distinct tiers: {n_distinct}")

    non_silent_recs = [r for r in records if r["mode_idx"] != 0]
    if non_silent_recs:
        print(f"  Non-silent events (first 10):")
        for r in non_silent_recs[:10]:
            print(f"    rnd {r['round']:>2d}: tier {r['mode_idx']} ({names[r['mode_idx']]}) | {r['cat']:>8s} \"{r['msg']}\" | tb={r['tone_bias']:+.3f} rsp={r['response_pre']:+.3f}")

    return records, dist, non_silent, n_distinct


def main():
    print("=" * 110)
    print("  30-Round Dialog Test — Tuned Sigmoid k=0.8452 / E0=-1.6076")
    print("=" * 110)

    # Pre-check: sigmoid value check
    print(f"\nSigmoid mapping (k={em._K_SAT}, E0={em._E0_SAT}):")
    for raw in [-3.0, -2.61, -2.5, -2.0, -1.5, -1.37, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]:
        e_s = em._saturate_e(raw)
        tb = 8.0 * (e_s - 0.5)
        print(f"  E={raw:+5.2f} → e_s={e_s:.4f} (tone={tb:+.3f})")

    # Verify episodic empty at start
    m = living_engine.cold_start_if_needed()
    print(f"\nStarting episodic_memory count: {len(m.get('user_model', {}).get('episodic_memory', []))}")

    # Run phases
    phase_a = run_phase("A: empty episodic_memory", mode="empty")
    phase_b = run_phase("B: single sigmoid-mapped memory (E=-2.0)", mode="inject", raw_e=-2.0)
    phase_c = run_phase("C: accumulated sigmoid memories (E=-2.0 each)", mode="accum", raw_e=-2.0)

    # Summary
    out = {
        "run": "tuned-sigmoid-30round",
        "timestamp": int(time.time()),
        "sigmoid_params": {"k": em._K_SAT, "E0": em._E0_SAT, "func": "sigmoid"},
        "phase_a_empty": {"records": phase_a[0], "distribution": dict(phase_a[1]), "non_silent": phase_a[2], "distinct_tiers": phase_a[3]},
        "phase_b_single": {"records": phase_b[0], "distribution": dict(phase_b[1]), "non_silent": phase_b[2], "distinct_tiers": phase_b[3]},
        "phase_c_accum": {"records": phase_c[0], "distribution": dict(phase_c[1]), "non_silent": phase_c[2], "distinct_tiers": phase_c[3]},
    }
    with open("active_memory/behavior_30round_tuned.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Final conclusion data
    print(f"\n{'='*110}")
    print("CONCLUSION (data only)")
    print(f"{'='*110}")
    print(f"  Phase A (empty):     non-silent = {phase_a[2]}/30, distinct tiers = {phase_a[3]}")
    print(f"  Phase B (single mem): non-silent = {phase_b[2]}/30, distinct tiers = {phase_b[3]}")
    print(f"  Phase C (accum mem): non-silent = {phase_c[2]}/30, distinct tiers = {phase_c[3]}")
    print()

    # If still silent anywhere, analyze the gap
    for label, phase in [("A", phase_a), ("B", phase_b), ("C", phase_c)]:
        recs = phase[0]
        if recs:
            tbs = [r["tone_bias"] for r in recs]
            rsps = [r["response_pre"] for r in recs]
            print(f"  Phase {label}: tone_bias ∈ [{min(tbs):+.4f}, {max(tbs):+.4f}]")
            print(f"  Phase {label}: response_pre ∈ [{min(rsps):+.4f}, {max(rsps):+.4f}]")
            # Tier thresholds
            tier_thresholds = {1: -1.386, 2: -0.405, 3: +0.405, 4: +1.386}
            for t, thr in tier_thresholds.items():
                above = sum(1 for r in rsps if r >= thr)
                print(f"    response_pre ≥ {thr:+.3f} (tier {t}+): {above}/{len(recs)}")
    print()


if __name__ == "__main__":
    main()
