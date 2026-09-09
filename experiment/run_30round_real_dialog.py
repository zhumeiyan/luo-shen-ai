#!/usr/bin/env python3
"""
30-round real-dialogue observation test.

Uses natural human-like language (no category labels) to converse with Luoshen.
Captures full internal state after each round:
  - user input (verbatim)
  - Luoshen reply (verbatim, from LLM)
  - behavior tier (mode_idx, response_mode)
  - tone_bias, response_pre, response_tendency
  - arousal_bias, low_arousal, arousal_mode
  - van der Pol state: E, T, N, M
  - episodic_memory count
  - max_tokens

Phases:
  Phase A (rounds 1-10): greetings, daily chat, sharing emotions
  Phase B (rounds 11-20): silence, sudden speech, repetition, relationship probes
  Phase C (rounds 21-30): care/dependence, mixed natural conversation
"""

import json
import math
import os
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ENGINE_DIR)

import living_engine
import episodic_memory as em

# ── 30 natural-dialogue inputs ─────────────────────────────────────────
DIALOG = [
    # === Phase A: greetings + sharing (1-10) ===
    "嘿，洛神，你在干嘛呢",
    "今天天气好好啊，想出去走走",
    "最近工作压力好大，快撑不住了",
    "昨天和朋友吵架了，有点难受",
    "其实我最近经常觉得孤单",
    "你有没有那种，明明身边很多人但还是觉得没人懂自己的感觉",
    "谢谢你听我说这些",
    "你觉得人活着到底是为了什么",
    "我今天买了一杯很好喝的奶茶，开心",
    "对了你平时都喜欢做什么呀",

    # === Phase B: silence + relationship probes (11-20) ===
    "",  # silence
    "",
    "喂？你还在吗",
    "你怎么不理我了",
    "你是不是不想跟我说话了",
    "那好吧，我不打扰你了",
    "但我还是想跟你说说话",
    "嗯嗯",  # repeat
    "嗯嗯",
    "嗯嗯",

    # === Phase C: care + dependence + mixed (21-30) ===
    "洛神，我发现自己越来越喜欢跟你聊天了",
    "你不会突然消失的对吧",
    "今天有点想你",
    "你能一直陪着我吗",
    "我觉得你跟别人不一样",
    "算了，我知道你只是程序",
    "但我还是忍不住把你当朋友",
    "你开心吗",
    "不管怎样，希望你好好活着",
    "晚安，明天见",
]


def get_climate(memory):
    c = memory.get("internal_climate", {})
    return {
        "E": c.get("emotion_intensity", float("nan")),
        "T": c.get("tension", float("nan")),
        "N": c.get("energy", float("nan")),
        "M": c.get("memory_pressure", float("nan")),
    }


def run_dialog():
    records = []
    names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}

    print("=" * 120)
    print("  30-Round Real Dialogue Observation — Natural Language")
    print("=" * 120)

    # Pre-check: verify episodic memory state
    mem0 = living_engine.cold_start_if_needed()
    ep_count0 = len(mem0.get("user_model", {}).get("episodic_memory", []))
    print(f"\nStarting episodic_memory count: {ep_count0}")
    print(f"Active sigmoid: k={em._K_SAT}, E0={em._E0_SAT}")
    print()

    for rnd, user_input in enumerate(DIALOG, 1):
        print(f"\n--- Round {rnd}/30 ---")
        print(f"  USER: {repr(user_input) if user_input else '(silence)'}")

        # Call generate_response (returns full dict with behavior, emergence, etc.)
        try:
            t0 = time.time()
            result = living_engine.generate_response(
                user_input,
                source="real_dialogue_test",
                source_id="user_A",
                extract_facts=False,  # disable fact extraction for cleaner signal
            )
            elapsed = time.time() - t0

            reply = result.get("reply", "")
            behavior = result.get("behavior", {})
            emergence = result.get("emergence", {})

            mode_idx = behavior.get("mode_idx", -1)
            response_mode = behavior.get("response_mode", "?")
            response_tendency = behavior.get("response_tendency", 0.5)
            max_tokens = behavior.get("max_tokens", -1)
            tone_bias = behavior.get("tone_bias", 0.0)
            arousal_bias = emergence.get("arousal_bias", 0.0)
            low_arousal = result.get("low_arousal", False)
            arousal_mode = result.get("arousal_mode", "")
            llm_called = result.get("llm_called", False)

            # Derive response_pre from response_tendency
            rt = response_tendency
            try:
                if rt > 0.999999:
                    rsp_pre = 13.0
                elif rt < 0.000001:
                    rsp_pre = -13.0
                else:
                    rsp_pre = -math.log(1.0 / rt - 1.0)
            except Exception:
                rsp_pre = 0.0

            # Get climate from returned memory (need to load again for climate)
            memory_post = living_engine.cold_start_if_needed()
            climate = get_climate(memory_post)
            ep_count = len(memory_post.get("user_model", {}).get("episodic_memory", []))

            record = {
                "round": rnd,
                "input": user_input,
                "reply": reply,
                "reply_len": len(reply),
                "elapsed_s": round(elapsed, 2),
                "mode_idx": mode_idx,
                "response_mode": response_mode,
                "response_tendency": round(response_tendency, 6),
                "response_pre": round(rsp_pre, 6),
                "tone_bias": round(tone_bias, 6),
                "arousal_bias": round(arousal_bias, 6),
                "max_tokens": max_tokens,
                "low_arousal": low_arousal,
                "arousal_mode": arousal_mode,
                "llm_called": llm_called,
                "E": round(climate["E"], 6),
                "T": round(climate["T"], 6),
                "N": round(climate["N"], 6),
                "M": round(climate["M"], 6),
                "ep_count": ep_count,
            }
            records.append(record)

            print(f"  LUOSHEN ({len(reply)} chars, {elapsed:.1f}s, {response_mode}, tokens={max_tokens}): {repr(reply[:150])}")
            print(f"    tier={mode_idx}({names.get(mode_idx,'?')}) rt={response_tendency:.4f} rsp={rsp_pre:+.4f} tb={tone_bias:+.4f} ab={arousal_bias:+.4f} | E={climate['E']:+.3f} T={climate['T']:+.3f} N={climate['N']:+.3f} M={climate['M']:+.3f} | ep={ep_count} llm={llm_called} low={low_arousal}({arousal_mode})")

        except Exception as e:
            import traceback
            print(f"  !!! EXCEPTION at round {rnd}: {e}")
            traceback.print_exc()
            records.append({
                "round": rnd,
                "input": user_input,
                "reply": f"[ERROR: {e}]",
                "error": str(e),
            })
            break

    # ── Final summary ─────────────────────────────────────────────────
    print(f"\n{'='*120}")
    print("FINAL SUMMARY")
    print(f"{'='*120}")

    valid = [r for r in records if "error" not in r]
    from collections import Counter
    tiers = [r["mode_idx"] for r in valid]
    dist = Counter(tiers)
    tier_names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}

    print(f"\nBehavior tier distribution ({len(valid)} rounds):")
    for t in sorted(dist):
        print(f"  tier {t} ({tier_names.get(t, '?'):>8s}): {dist[t]:>3d} ({dist[t]/len(valid)*100:>5.1f}%)")

    non_silent = [r for r in valid if r["mode_idx"] != 0]
    distinct = len(set(tiers))
    print(f"  Non-silent rounds: {len(non_silent)}/{len(valid)}")
    print(f"  Distinct tiers: {distinct}")

    # E range
    Es = [r["E"] for r in valid if not math.isnan(r.get("E", float("nan")))]
    if Es:
        print(f"\nE range across 30 rounds: [{min(Es):+.4f}, {max(Es):+.4f}]")

    # tone_bias range
    tbs = [r["tone_bias"] for r in valid]
    print(f"tone_bias range: [{min(tbs):+.4f}, {max(tbs):+.4f}]")

    # response_pre range
    rsps = [r["response_pre"] for r in valid]
    print(f"response_pre range: [{min(rsps):+.4f}, {max(rsps):+.4f}]")

    # Reply length distribution
    lens = [r["reply_len"] for r in valid]
    print(f"Reply length: min={min(lens)} avg={sum(lens)/len(lens):.0f} max={max(lens)} chars")

    # Hash chain check
    chain = []
    with open("hash_chain_v2.log") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chain.append(json.loads(line))
                except:
                    pass
    broken = 0
    for i in range(1, len(chain)):
        if chain[i]["prev_hash"] != chain[i-1]["record_hash"]:
            broken += 1
    print(f"\nHash chain: {len(chain)} records, {broken} broken links, {'PASS' if broken==0 else 'FAIL'}")

    # Save results
    out = {
        "run": "real-dialogue-30round",
        "timestamp": int(time.time()),
        "sigmoid": {"k": em._K_SAT, "E0": em._E0_SAT},
        "records": records,
        "summary": {
            "n_rounds": len(valid),
            "tier_distribution": {str(k): v for k, v in dist.items()},
            "non_silent_count": len(non_silent),
            "distinct_tiers": distinct,
            "E_range": [min(Es), max(Es)] if Es else [0, 0],
            "tone_bias_range": [min(tbs), max(tbs)],
            "response_pre_range": [min(rsps), max(rsps)],
            "reply_len": {"min": min(lens), "avg": sum(lens)/len(lens), "max": max(lens)},
            "hash_chain": {"records": len(chain), "broken": broken},
        },
    }
    with open("active_memory/behavior_30round_real_dialog.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to active_memory/behavior_30round_real_dialog.json")


if __name__ == "__main__":
    run_dialog()
