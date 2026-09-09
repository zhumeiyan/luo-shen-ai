#!/usr/bin/env python3
"""
20-round real-style conversation test after sigmoid e_s fix.

Inputs mix styles: neutral/light_neg/heavy_neg/pressure/repeat/diversity.
Records tone_bias, response_pre, sigmoid output, mode_idx each round.
"""

import json
import math
import os
import random
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ENGINE_DIR)

import living_engine

# ── Constants for reconstruction ─────────────────────────────────────────
_NARRATIVE_TENDENCY_BOOST = 5.0
_R_K_COH_R = 0.8
_PRESSURE_K = 0.4

random.seed(7)

# Real-diverse input pool (~20 distinct styles)
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

def reconstruct_response_pre(memory, emergence, behavior_ret):
    tone_bias        = emergence.get("tone_bias", 0.0)
    arousal_bias     = emergence.get("arousal_bias", 0.0)
    narrative_pot    = emergence.get("narrative_potential", 0.0)
    _phase    = memory.get("self_model",{}).get("ring_state",{}).get("phase", 0.0)
    _rcoh     = memory.get("self_model",{}).get("ring_state",{}).get("r_coherence", 0.5)
    _narr_boost = _NARRATIVE_TENDENCY_BOOST * (1.0 + _R_K_COH_R * (_rcoh - 0.5))
    _phase_bias = 0.03 * math.sin(_phase)
    _pressure_term = behavior_ret.get("pressure_term", 0.0)
    _internal_drive = behavior_ret.get("internal_drive", 0.0)
    _presence_bias  = behavior_ret.get("presence_bias", 0.0)
    response_pre = (arousal_bias + 0.5 * tone_bias
                    + _narr_boost * narrative_pot
                    + _phase_bias + _pressure_term
                    + _internal_drive + _presence_bias)
    sigmoid_out = 1.0 / (1.0 + math.exp(-response_pre))
    mode_idx = int(sigmoid_out * 4.999)
    return response_pre, sigmoid_out, mode_idx, tone_bias, arousal_bias, narrative_pot


def run():
    records = []
    print("=== 20-round dialog test (post sigmoid fix) ===")
    print(f"{'rnd':>3} {'cat':>8} {'msg':>12} {'tone_bias':>10} {'rsp_pre':>9} {'sig':>7} {'tier':>4} {'max_tok':>7}")
    print("-" * 75)

    for rnd, (cat, msg) in enumerate(INPUTS):
        silence = (msg == "")
        if not silence:
            # two environment ticks to match live flow pattern
            try:
                living_engine.environment_tick(force=True)
                living_engine.environment_tick(force=True)
            except Exception as e:
                print(f"env_tick CRASH: {e}")
                break

        try:
            memory = living_engine.cold_start_if_needed()
            emergence = living_engine._emergence_log(memory)
            tier = living_engine._select_behavior(memory, emergence)
            mode_idx_actual = tier.get("mode_idx", -1)
            rsp_pre, sig, mode_idx_reconstructed, tb, ab, npot = reconstruct_response_pre(
                memory, emergence, tier)
            records.append({
                "round": rnd + 1,
                "cat": cat, "msg": msg[:16],
                "tone_bias": round(tb, 5),
                "arousal_bias": round(ab, 5),
                "narr_pot": round(npot, 5),
                "response_pre": round(rsp_pre, 4),
                "sigmoid": round(sig, 6),
                "mode_idx": mode_idx_actual,
                "max_tokens": tier.get("max_tokens", -1),
                "input": msg,
            })
            print(f"{rnd+1:>3d} {cat:>8s} {msg:>16s} {tb:>+10.4f} {rsp_pre:>+9.4f} {sig:>7.4f} {mode_idx_actual:>4d} {tier.get('max_tokens',-1):>7d}")
        except Exception as e:
            print(f"CRASH round {rnd}: {e}")
            break

    # Behavior tier distribution
    from collections import Counter
    tiers = [r["mode_idx"] for r in records]
    dist = Counter(tiers)
    non_silent = [r for r in records if r["mode_idx"] != 0]
    print()
    print("=== Tier distribution ===")
    names = {0:"silent",1:"brief",2:"short",3:"normal",4:"engaged"}
    for t in sorted(dist):
        print(f"  tier {t} ({names.get(t,'?'):>8s}): {dist[t]:>3d} ({dist[t]/len(records)*100:>5.1f}%)")
    print(f"Non-silent rounds: {len(non_silent)}")
    if non_silent:
        print("\nNon-silent events:")
        for r in non_silent:
            print(f"  round {r['round']:>2d}: tier {r['mode_idx']} | '{r['cat']:>8s}' \"{r['input']}\"")

    with open("active_memory/behavior_20round_test.json", "w") as f:
        json.dump({"run": "sigmoid-fix-test-20round", "records": records,
                   "tier_distribution": dict(dist),
                   "n_non_silent": len(non_silent)}, f, ensure_ascii=False, indent=2)
    print("\nSaved to active_memory/behavior_20round_test.json")
    print("=== DONE ===")


if __name__ == "__main__":
    run()
