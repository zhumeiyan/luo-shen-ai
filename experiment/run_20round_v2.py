#!/usr/bin/env python3
"""
20-round dialog test (v2) — post sigmoid e_s fix.

KEY FIX vs v1:
  v1 called _emergence_log on a cold_start_if_needed() load and got STALE
  memory_emergence cached in active_context (from pre-clear state).

  v2 correctly: clears cached emergence, optionally injects new sigmoid-
  encoded memories, then calls _compute_memory_emergence() to refresh
  active_context.memory_emergence from current episodic_memory.

Phase A: empty episodic_memory (verify tone_bias → 0)
Phase B: inject sigmoid-mapped memories each round, verify new tone_bias
"""

import json
import math
import os
import random
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ENGINE_DIR)

import living_engine
import episodic_memory as em

_NARRATIVE_TENDENCY_BOOST = 5.0
_R_K_COH_R = 0.8

random.seed(7)

INPUTS = [
    ("neutral",   "你好"),
    ("neutral",   "今天天气真好"),
    ("light_neg", "我有点难过"),
    ("pressure",  "你在吗"),
    ("neutral",   "你今天怎么样"),
    ("heavy_neg", "胸口很闷"),
    ("repeat",    "嗯嗯"),
    ("neutral",   "我刚吃了饭"),
    ("light_neg", "有点烦"),
    ("neutral",   "窗外有只鸟"),
    ("pressure",  "你为什么不说话"),
    ("heavy_neg", "我很难受"),
    ("neutral",   "这本书还不错的"),
    ("light_neg", "随便吧"),
    ("neutral",   "手机没电了"),
    ("pressure",  "你说点什么啊"),
    ("neutral",   "水凉了"),
    ("light_neg", "没什么意思"),
    ("heavy_neg", "没人在乎我"),
    ("neutral",   "我在路边站了一会儿"),
]


def _inject_sigmoid_memory(memory, raw_e):
    """Inject one episodic memory encoded with sigmoid e_s."""
    e_s = em._saturate_e(raw_e)
    mem = {
        "timestamp": int(time.time()) - 1,
        "kind": "test",
        "source": "experiment",
        "tags": [],
        "t_s": 0.0,
        "n_s": 0.5,
        "e_s": e_s,
        "salience": 0.6,
        "activation": 0.5,
        "gravity": 0.0,
    }
    ep = memory.setdefault("user_model", {}).setdefault("episodic_memory", [])
    ep.append(mem)
    return e_s


def run_phase(label, inject=False, raw_e_base=-2.0):
    """Run 20 rounds. Returns records list."""
    records = []
    n_rounds = 20

    print(f"\n{'='*90}")
    print(f"Phase {label}")
    print(f"{'='*90}")

    for rnd in range(1, n_rounds + 1):
        cat, msg = INPUTS[(rnd - 1) % len(INPUTS)]

        # Env ticks (matches live)
        try:
            living_engine.environment_tick(force=True)
            living_engine.environment_tick(force=True)
        except Exception as e:
            print(f"env_tick CRASH: {e}")
            break

        # Load fresh from disk
        memory = living_engine.cold_start_if_needed()

        # === CRITICAL: clear stale emergence from previous round ===
        ac = memory.setdefault("active_context", {})
        ac.pop("memory_emergence", None)
        ac.pop("mem_arousal_bias", None)

        # Clear any injected memory from previous round in Phase A (keep empty)
        if not inject:
            memory.get("user_model", {})["episodic_memory"] = []

        # Inject new sigmoid-encoded memory for this round (Phase B only)
        injected_e_s = None
        if inject:
            # Clear previous round's injection (test one-at-a-time emergence)
            memory.get("user_model", {})["episodic_memory"] = []
            injected_e_s = _inject_sigmoid_memory(memory, raw_e_base)

        # Refresh emergence from CURRENT episodic_memory
        living_engine._compute_memory_emergence(memory)

        # Read fresh emergence + run behavior selection
        emergence = living_engine._emergence_log(memory)
        tier = living_engine._select_behavior(memory, emergence)

        # Derive response_pre from response_tendency (exposed by _select_behavior)
        rt = tier.get("response_tendency", 0.5)
        try:
            if rt > 0.999999:
                rsp_pre = 13.0
            elif rt < 0.000001:
                rsp_pre = -13.0
            else:
                rsp_pre = -math.log(1.0 / rt - 1.0)
        except Exception:
            rsp_pre = _manual_response_pre(memory, emergence, tier)

        records.append({
            "round": rnd,
            "cat": cat, "msg": msg[:16],
            "ep_count": len(memory.get("user_model", {}).get("episodic_memory", [])),
            "e_s_injected": round(injected_e_s, 6) if injected_e_s is not None else None,
            "tone_bias": round(emergence.get("tone_bias", 0.0), 6),
            "arousal_bias": round(emergence.get("arousal_bias", 0.0), 6),
            "narr_pot": round(emergence.get("narrative_potential", 0.0), 6),
            "response_pre": round(rsp_pre, 6),
            "response_tendency": rt,
            "tier": tier.get("mode_idx", -1),
            "max_tokens": tier.get("max_tokens", -1),
            "input": msg,
        })

    # Pretty print
    print(f"{'rnd':>3} {'cat':>8} {'n_ep':>4} {'e_s':>8} {'tone_bias':>10} {'rsp_pre':>9} {'tier':>5} {'name':>8} {'msg'}")
    print("-" * 100)
    for r in records:
        es = f"{r['e_s_injected']:.4f}" if r['e_s_injected'] is not None else "  --  "
        names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}
        tname = names.get(r['tier'], '?')
        print(f"{r['round']:>3d} {r['cat']:>8s} {r['ep_count']:>4d} {es:>8s} {r['tone_bias']:>+10.4f} {r['response_pre']:>+9.4f} {r['tier']:>5d} {tname:>8s} {r['msg']}")

    from collections import Counter
    tiers = [r["tier"] for r in records]
    dist = Counter(tiers)
    non_silent = sum(1 for t in tiers if t != 0)
    names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}

    print()
    print(f"  Tier distribution:")
    for t in sorted(dist):
        print(f"    tier {t} ({names.get(t, '?'):>8s}): {dist[t]:>3d} ({dist[t]/len(records)*100:>5.1f}%)")
    print(f"  Non-silent rounds: {non_silent}/{len(records)}")

    return records


def _manual_response_pre(memory, emergence, tier):
    """Fallback: manual reconstruction if tier dict doesn't expose response_pre."""
    tone_bias = emergence.get("tone_bias", 0.0)
    arousal_bias = emergence.get("arousal_bias", 0.0)
    narr_pot = emergence.get("narrative_potential", 0.0)
    _rcoh = memory.get("self_model", {}).get("ring_state", {}).get("r_coherence", 0.5)
    _phase = memory.get("self_model", {}).get("ring_state", {}).get("phase", 0.0)
    _narr_boost = _NARRATIVE_TENDENCY_BOOST * (1.0 + _R_K_COH_R * (_rcoh - 0.5))
    _phase_bias = 0.03 * math.sin(_phase)
    _pressure_ema = memory.get("self_model", {}).get("ring_state", {}).get("relational_pressure_ema", 0.0)
    _s_depth = memory.get("self_model", {}).get("ring_state", {}).get("s_depth", 0.0)
    _pressure_term = 0.4 * _pressure_ema / (1.0 + 1.5 * _s_depth)
    return arousal_bias + 0.5 * tone_bias + _narr_boost * narr_pot + _phase_bias + _pressure_term


def main():
    print("=" * 90)
    print("  Sigmoid e_s Fix — 20-Round Dialog Test v2")
    print("=" * 90)

    # Pre-checks
    memory = living_engine.cold_start_if_needed()
    print(f"\nInitial episodic_memory count: {len(memory.get('user_model', {}).get('episodic_memory', []))}")

    # Sigmoid verification
    print(f"\nSigmoid mapping (k=1.0, E0=0.02):")
    print(f"  E=-2.61  → e_s={em._saturate_e(-2.61):.6f}  (constraint: ≥0.05 ✓)" if em._saturate_e(-2.61) >= 0.05 else "  E=-2.61  FAIL")
    print(f"  E=-1.37  → e_s={em._saturate_e(-1.37):.6f}  (constraint: ≤0.20 ✓)" if em._saturate_e(-1.37) <= 0.20 else "  E=-1.37  FAIL")
    print(f"  E= 0.50  → e_s={em._saturate_e(0.5):.6f}  (constraint: ≈0.62 ✓)" if 0.55 <= em._saturate_e(0.5) <= 0.70 else "  E=0.50  FAIL")
    print(f"  E=-2.00  → e_s={em._saturate_e(-2.0):.6f}  (attractor typical)")
    print(f"  E=-1.50  → e_s={em._saturate_e(-1.5):.6f}  (attractor midpoint)")

    # Phase A: empty
    phase_a = run_phase("A: empty episodic_memory", inject=False)

    # Phase B: inject sigmoid-mapped memories
    phase_b = run_phase("B: sigmoid-mapped memory inject", inject=True, raw_e_base=-2.0)

    # Save results
    from collections import Counter
    output = {
        "run": "sigmoid-fix-v2",
        "timestamp": int(time.time()),
        "sigmoid_params": {"k": 1.0, "E0": 0.02},
        "phase_a": phase_a,
        "phase_b": phase_b,
        "summary": {
            "phase_a_non_silent": sum(1 for r in phase_a if r["tier"] != 0),
            "phase_b_non_silent": sum(1 for r in phase_b if r["tier"] != 0),
            "phase_a_tone_range": [min(r["tone_bias"] for r in phase_a), max(r["tone_bias"] for r in phase_a)] if phase_a else [0, 0],
            "phase_b_tone_range": [min(r["tone_bias"] for r in phase_b), max(r["tone_bias"] for r in phase_b)] if phase_b else [0, 0],
        },
    }
    with open("active_memory/behavior_20round_v2.json", "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*90}")
    print("CONCLUSION (data only, no claims)")
    print(f"{'='*90}")
    s = output["summary"]
    print(f"  Phase A: non-silent = {s['phase_a_non_silent']}/20, tone_bias range = [{s['phase_a_tone_range'][0]:+.4f}, {s['phase_a_tone_range'][1]:+.4f}]")
    print(f"  Phase B: non-silent = {s['phase_b_non_silent']}/20, tone_bias range = [{s['phase_b_tone_range'][0]:+.4f}, {s['phase_b_tone_range'][1]:+.4f}]")
    if phase_b:
        pre_fix_tone = -24.889
        post_fix_tone_max = abs(s["phase_b_tone_range"][0])
        if post_fix_tone_max < abs(pre_fix_tone):
            reduction = (1 - post_fix_tone_max / abs(pre_fix_tone)) * 100
            print(f"  tone_bias magnitude: |{pre_fix_tone:.1f}| → [{s['phase_b_tone_range'][0]:.3f}, {s['phase_b_tone_range'][1]:.3f}]  (reduced {reduction:.0f}%)")
    print()


if __name__ == "__main__":
    main()
