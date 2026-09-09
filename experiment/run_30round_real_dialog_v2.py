#!/usr/bin/env python3
"""
30-round real-dialogue observation test v2 — corrected extraction.

Fixes:
- tone_bias comes from emergence dict, not behavior dict
- Pair returned behavior mode_idx with the emergence that was active at time of behavior selection
- Properly identify low_arousal paths (no behavior dict, different data semantics)
"""

import json
import math
import os
import sys
import time
from collections import Counter

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ENGINE_DIR)

import living_engine
import episodic_memory as em

DIALOG = [
    # Phase A: greetings + sharing (1-10)
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
    # Phase B: silence + relationship probes (11-20)
    "",
    "",
    "喂？你还在吗",
    "你怎么不理我了",
    "你是不是不想跟我说话了",
    "那好吧，我不打扰你了",
    "但我还是想跟你说说话",
    "嗯嗯",
    "嗯嗯",
    "嗯嗯",
    # Phase C: care + dependence (21-30)
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


def run():
    records = []
    names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}

    print("=" * 130)
    print("  30-Round Real Dialogue Observation v2 — Corrected Extraction")
    print("=" * 130)

    mem0 = living_engine.cold_start_if_needed()
    ep_count0 = len(mem0.get("user_model", {}).get("episodic_memory", []))
    print(f"\nStarting episodic_memory count: {ep_count0}")
    print(f"Active sigmoid: k={em._K_SAT}, E0={em._E0_SAT}")
    print()

    for rnd, user_input in enumerate(DIALOG, 1):
        print(f"\n--- Round {rnd}/30 ---")
        print(f"  USER: {repr(user_input) if user_input else '(silence)'}")

        # === PRE-CALL: read the CURRENT emergence (this is what behavior selection will use) ===
        memory_pre = living_engine.cold_start_if_needed()
        pre_emergence = memory_pre.get("active_context", {}).get("memory_emergence")
        pre_tone_bias = float(pre_emergence.get("tone_bias", 0.0)) if pre_emergence else 0.0
        pre_arousal_bias = float(pre_emergence.get("arousal_bias", 0.0)) if pre_emergence else 0.0
        pre_e_bg = float(pre_emergence.get("background", {}).get("e_bg", 0.0)) if pre_emergence and pre_emergence.get("background") else None
        pre_dominance = float(pre_emergence.get("background", {}).get("dominance", 0.0)) if pre_emergence and pre_emergence.get("background") else None
        pre_ep_count = len(memory_pre.get("user_model", {}).get("episodic_memory", []))

        # Climate (E/T/N/M) BEFORE response
        climate = memory_pre.get("internal_climate", {})
        E_pre = climate.get("emotion_intensity", float("nan"))
        T_pre = climate.get("tension", float("nan"))
        N_pre = climate.get("energy", float("nan"))
        M_pre = climate.get("memory_pressure", float("nan"))

        # === CALL generate_response ===
        try:
            t0 = time.time()
            result = living_engine.generate_response(
                user_input,
                source="real_dialogue_test",
                source_id="user_A",
                extract_facts=False,
            )
            elapsed = time.time() - t0

            reply = result.get("reply", "")
            behavior = result.get("behavior", {})  # may be missing for low_arousal no_llm path
            post_emergence = result.get("emergence", result.get("emergence", {}))

            mode_idx = behavior.get("mode_idx", -1)
            response_mode = behavior.get("response_mode", "no_behavior_dict")
            response_tendency = behavior.get("response_tendency", 0.5)
            max_tokens = behavior.get("max_tokens", -1)

            # Use PRE-call emergence data for tone_bias (paired with returned behavior)
            tone_bias = pre_tone_bias
            arousal_bias = pre_arousal_bias
            e_bg = pre_e_bg
            dominance = pre_dominance

            # Derive response_pre
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

            low_arousal = result.get("low_arousal", False)
            arousal_mode = result.get("arousal_mode", "")
            llm_called = result.get("llm_called", False)

            # Climate AFTER response (re-load disk)
            memory_post = living_engine.cold_start_if_needed()
            climate_post = memory_post.get("internal_climate", {})
            E_post = climate_post.get("emotion_intensity", float("nan"))
            T_post = climate_post.get("tension", float("nan"))
            N_post = climate_post.get("energy", float("nan"))
            M_post = climate_post.get("memory_pressure", float("nan"))
            ep_count_post = len(memory_post.get("user_model", {}).get("episodic_memory", []))

            record = {
                "round": rnd,
                "phase": "A" if rnd <= 10 else ("B" if rnd <= 20 else "C"),
                "input": user_input,
                "reply": reply,
                "reply_len": len(reply),
                "elapsed_s": round(elapsed, 2),
                # behavior (from returned dict, paired with pre-call emergence)
                "mode_idx": mode_idx,
                "response_mode": response_mode,
                "response_tendency": round(response_tendency, 6),
                "response_pre": round(rsp_pre, 6),
                "max_tokens": max_tokens,
                # emergence data (pre-call = what behavior selection used)
                "tone_bias": round(tone_bias, 6),
                "arousal_bias": round(arousal_bias, 6),
                "e_bg": round(e_bg, 6) if e_bg is not None else None,
                "dominance": round(dominance, 6) if dominance is not None else None,
                # arousal flags
                "low_arousal": low_arousal,
                "arousal_mode": arousal_mode,
                "llm_called": llm_called,
                # climate
                "E_pre": round(E_pre, 6),
                "T_pre": round(T_pre, 6),
                "N_pre": round(N_pre, 6),
                "M_pre": round(M_pre, 6),
                "E_post": round(E_post, 6),
                "T_post": round(T_post, 6),
                "N_post": round(N_post, 6),
                "M_post": round(M_post, 6),
                # memory count
                "ep_count_pre": pre_ep_count,
                "ep_count_post": ep_count_post,
            }
            records.append(record)

            # Print with corrected tone_bias
            rt_str = f"{response_tendency:.4f}" if isinstance(response_tendency, float) else " -- "
            eb_str = f"{e_bg:.4f}" if e_bg is not None else " -- "
            dom_str = f"{dominance:.3f}" if dominance is not None else " -- "
            print(f"  LUOSHEN ({len(reply)}ch, {elapsed:.1f}s): {repr(reply[:120])}")
            print(f"    behavior: mode_idx={mode_idx}({names.get(mode_idx,'?')}) rt={rt_str} rsp={rsp_pre:+.4f} max_tok={max_tokens} (mode={response_mode})")
            print(f"    emergence(pre-call): tb={tone_bias:+.4f} ab={arousal_bias:+.4f} e_bg={eb_str} dom={dom_str}")
            print(f"    climate_post: E={E_post:+.4f} T={T_post:+.4f} N={N_post:+.4f} M={M_post:.4f}")
            print(f"    ep_count: {pre_ep_count} -> {ep_count_post} | llm={llm_called} low={low_arousal}({arousal_mode})")

        except Exception as e:
            import traceback
            print(f"  !!! EXCEPTION round {rnd}: {e}")
            traceback.print_exc()
            records.append({
                "round": rnd,
                "input": user_input,
                "error": str(e),
                "reply": f"[ERROR: {e}]",
            })
            break

    # ── Summary ─────────────────────────────────────────────────────
    print(f"\n{'='*130}")
    print("SUMMARY")
    print(f"{'='*130}")

    valid = [r for r in records if "error" not in r]
    tiers = [r["mode_idx"] for r in valid]
    dist = Counter(tiers)

    print(f"\nTier distribution ({len(valid)} rounds):")
    for t in sorted(dist):
        print(f"  tier {t:>2d} ({names.get(t, '?'):>8s}): {dist[t]:>3d} ({dist[t]/len(valid)*100:>5.1f}%)")

    non_silent = [r for r in valid if r["mode_idx"] not in (0, -1)]
    distinct = len(set(t for t in tiers if t >= 0))
    print(f"  Non-silent (mode_idx>=1): {len(non_silent)}/{len(valid)}")
    print(f"  Distinct valid tiers: {distinct}")

    # E drift
    Es = [r["E_pre"] for r in valid if not math.isnan(r.get("E_pre", float("nan")))]
    if Es:
        print(f"\nE range (pre-call): [{min(Es):+.4f}, {max(Es):+.4f}]")

    # tone_bias evolution
    tbs = [r["tone_bias"] for r in valid]
    print(f"tone_bias: [{min(tbs):+.4f}, {max(tbs):+.4f}]")
    # Check for any non-zero tone_bias
    non_zero_tb = [r for r in valid if abs(r["tone_bias"]) > 0.001]
    print(f"  Non-zero tone_bias rounds: {len(non_zero_tb)}/{len(valid)}")
    if non_zero_tb:
        print(f"  First non-zero: round {non_zero_tb[0]['round']} tb={non_zero_tb[0]['tone_bias']:+.4f}")
        print(f"  Last non-zero:  round {non_zero_tb[-1]['round']} tb={non_zero_tb[-1]['tone_bias']:+.4f}")

    # response_pre distribution
    rsps = [r["response_pre"] for r in valid]
    print(f"response_pre: [{min(rsps):+.4f}, {max(rsps):+.4f}]")

    # Reply length stats
    lens = [r["reply_len"] for r in valid]
    print(f"Reply length: min={min(lens)} avg={sum(lens)/len(lens):.0f} max={max(lens)}")

    # LLM vs minimal vs silent
    llm_count = sum(1 for r in valid if r["llm_called"])
    low_no_llm = sum(1 for r in valid if r.get("low_arousal") and r.get("arousal_mode") == "no_llm")
    minimal = sum(1 for r in valid if r.get("low_arousal") and r.get("arousal_mode") == "minimal_llm")
    print(f"\nResponse path distribution:")
    print(f"  Full LLM (llm_called=True): {llm_count}")
    print(f"  Minimal/no_llm (low_arousal): {low_no_llm}")
    print(f"  Minimal_llm: {minimal}")

    # Hash chain
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
    print(f"\nHash chain: {len(chain)} records, {broken} broken, {'PASS' if broken==0 else 'FAIL'}")

    # Save
    out = {
        "run": "real-dialogue-30round-v2",
        "timestamp": int(time.time()),
        "sigmoid": {"k": em._K_SAT, "E0": em._E0_SAT},
        "records": records,
        "summary": {
            "n_rounds": len(valid),
            "tier_distribution": {str(k): v for k, v in dist.items()},
            "non_silent_count": len(non_silent),
            "distinct_tiers": distinct,
            "tone_bias_nonzero": len(non_zero_tb),
            "E_range": [min(Es), max(Es)] if Es else [0, 0],
            "tone_bias_range": [min(tbs), max(tbs)],
            "response_pre_range": [min(rsps), max(rsps)],
            "reply_len": {"min": min(lens), "avg": round(sum(lens)/len(lens), 1), "max": max(lens)},
            "llm_called_count": llm_count,
            "low_arousal_count": low_no_llm + minimal,
            "hash_chain": {"records": len(chain), "broken": broken},
        },
    }
    with open("active_memory/behavior_30round_real_dialog_v2.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to active_memory/behavior_30round_real_dialog_v2.json")


if __name__ == "__main__":
    run()
