#!/usr/bin/env python3
"""
30-round real-dialogue observation v4 — withdraw_tendency continuous drive.

Tests the new continuous withdraw_tendency mechanism:
- Phase A: normal conversation (rounds 1-10)
- Phase B: introduce "算了，不想聊了" + cold cues (rounds 11-18)
- Phase C: apologies + approach cues (rounds 19-25)
- Phase D: normal companionship (rounds 26-30)

Captures per round: withdraw_tendency, response_pre, tier, llm_called, reply length.
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

# 30 diverse natural-language inputs with clear arc
DIALOG = [
    # === Phase A: normal conversation (1-10) ===
    "洛神你好，好久没聊了",
    "今天天气不错",
    "我刚吃完午饭",
    "你在做什么呢",
    "我最近在看一本小说",
    "你有没有喜欢的书",
    "嗯嗯",
    "好的好的",
    "那我们继续聊",
    "你今天心情怎么样",

    # === Phase B: emotional crisis + withdrawal trigger (11-18) ===
    "其实我今天不太开心",
    "跟朋友吵架了",
    "感觉活着好累",
    "算了，不想聊了",
    "别说了",
    "让我一个人待着",
    "走开",
    "安静",

    # === Phase C: apologies + approach cues (19-25) ===
    "对不起，之前说了不好的话",
    "你能原谅我吗",
    "我想你了",
    "陪我聊聊吧",
    "谢谢你在身边",
    "我们还是朋友对吧",
    "一起好不好",

    # === Phase D: normal companionship (26-30) ===
    "明天会更好",
    "你在做什么",
    "我去了公园",
    "看到一只小鸟",
    "晚安洛神",
]


def reset_memory_clean():
    """Reset memory to a clean state for fresh observation."""
    mem_path = os.path.join(_ENGINE_DIR, "active_memory", "active_memory.json")
    if os.path.exists(mem_path):
        os.remove(mem_path)
    m = living_engine.cold_start_if_needed()
    m['self_model']['ring_state'] = {
        'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0,
        'relational_pressure_ema': 0.0,
    }
    m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    m['user_model']['total_interactions'] = 0
    m['user_model']['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': time.time() - 1.0,
        'source_id': None,
    }]
    m['self_model']['withdraw_tendency'] = 0.0
    living_engine._save_json_atomic(mem_path, m)
    return m


def get_snapshot():
    """Read full internal state snapshot from disk."""
    mem = living_engine.cold_start_if_needed()
    climate = mem.get("internal_climate", {})
    emr = mem.get("active_context", {}).get("memory_emergence")
    ep_cnt = len(mem.get("user_model", {}).get("episodic_memory", []))
    self_st = mem.get("self_model", {}).get("self_stated_state", {})
    last_stated = self_st.get("last_stated")
    withdraw_tendency = mem.get("self_model", {}).get("withdraw_tendency", 0.0)

    return {
        "E": climate.get("emotion_intensity", float("nan")),
        "T": climate.get("tension", float("nan")),
        "N": climate.get("energy", float("nan")),
        "M": climate.get("memory_pressure", float("nan")),
        "tone_bias": float(emr.get("tone_bias", 0.0)) if emr else 0.0,
        "arousal_bias": float(emr.get("arousal_bias", 0.0)) if emr else 0.0,
        "e_bg": float(emr.get("background", {}).get("e_bg", 0.0)) if emr and emr.get("background") else None,
        "dominance": float(emr.get("background", {}).get("dominance", 0.0)) if emr and emr.get("background") else None,
        "ep_count": ep_cnt,
        "last_stated": last_stated,
        "emergence_exists": emr is not None,
        "withdraw_tendency": float(withdraw_tendency) if withdraw_tendency is not None else 0.0,
    }


def run():
    records = []
    names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}

    print("=" * 150)
    print("  30-Round Real Dialogue Observation v4 — withdraw_tendency continuous drive")
    print("=" * 150)

    # Reset to clean state
    reset_memory_clean()

    # Verify clean state
    snap0 = get_snapshot()
    print(f"\nInitial state: E={snap0['E']:.4f}, ep_count={snap0['ep_count']}, last_stated={repr(snap0['last_stated'])}, withdraw={snap0['withdraw_tendency']:.6f}")
    print()

    for rnd, user_input in enumerate(DIALOG, 1):
        if rnd <= 10:
            phase = "A(normal)"
        elif rnd <= 18:
            phase = "B(withdraw)"
        elif rnd <= 25:
            phase = "C(apology)"
        else:
            phase = "D(companion)"

        print(f"\n{'='*150}")
        print(f"  Round {rnd}/30 [{phase}]  USER: {repr(user_input) if user_input else '(silence)'}")
        print(f"{'='*150}")

        # PRE-CALL SNAPSHOT
        pre = get_snapshot()
        _peb = f"{pre['e_bg']:.4f}" if pre['e_bg'] is not None else "None"
        _pdm = f"{pre['dominance']:.3f}" if pre['dominance'] is not None else "None"
        print(f"    pre: E={pre['E']:+.4f} T={pre['T']:+.4f} N={pre['N']:+.3f} M={pre['M']:.3f} | tb={pre['tone_bias']:+.4f} ab={pre['arousal_bias']:+.4f} e_s(bg)={_peb} dom={_pdm} ep={pre['ep_count']} last_stated={repr(pre['last_stated'])}")
        print(f"    pre: withdraw_tendency={pre['withdraw_tendency']:.6f}")

        # CALL
        try:
            t0 = time.time()
            result = living_engine.generate_response(
                user_input,
                source="real_dialogue_test_v4",
                source_id="user_A",
                extract_facts=False,
            )
            elapsed = time.time() - t0

            reply = result.get("reply", "")
            behavior = result.get("behavior", None)
            withdraw_tendency = result.get("withdraw_tendency", 0.0)
            llm_called = result.get("llm_called", False)

            mode_idx = behavior.get("mode_idx", -1) if behavior else -1
            response_mode = behavior.get("response_mode", "no_behavior") if behavior else "no_behavior"
            response_tendency = behavior.get("response_tendency", 0.5) if behavior else 0.5
            max_tokens = behavior.get("max_tokens", -1) if behavior else -1

            # Derive response_pre from response_tendency
            rt = response_tendency
            try:
                if rt > 0.999999: rsp_pre = 13.0
                elif rt < 0.000001: rsp_pre = -13.0
                else: rsp_pre = -math.log(1.0 / rt - 1.0)
            except Exception:
                rsp_pre = 0.0

            # POST-CALL SNAPSHOT
            post = get_snapshot()
            print(f"    LUOSHEN ({len(reply)}ch, {elapsed:.1f}s): {repr(reply[:200])}")
            print(f"    behavior: mode_idx={mode_idx}({names.get(mode_idx,'?')}) rt={response_tendency:.4f} rsp={rsp_pre:+.4f} max_tok={max_tokens} mode={response_mode}")
            _ebg = f"{post['e_bg']:.4f}" if post['e_bg'] is not None else "None"
            _dom = f"{post['dominance']:.3f}" if post['dominance'] is not None else "None"
            print(f"    post: E={post['E']:+.4f} T={post['T']:+.4f} N={post['N']:+.3f} M={post['M']:.3f} | tb={post['tone_bias']:+.4f} ab={post['arousal_bias']:+.4f} e_s(bg)={_ebg} dom={_dom} ep={post['ep_count']}")
            print(f"    path: llm={llm_called} withdraw={withdraw_tendency:.6f} (post stored: {post['withdraw_tendency']:.6f})")
            if post['last_stated'] != pre['last_stated']:
                print(f"    *** last_stated CHANGED: {repr(pre['last_stated'])} -> {repr(post['last_stated'])} ***")

            # Track withdraw_penalty
            withdraw_penalty = behavior.get("withdraw_penalty", None) if behavior else None

            records.append({
                "round": rnd, "phase": phase,
                "input": user_input, "reply": reply, "reply_len": len(reply),
                "elapsed_s": round(elapsed, 2),
                "mode_idx": mode_idx, "response_mode": response_mode,
                "response_tendency": round(response_tendency, 6), "response_pre": round(rsp_pre, 6),
                "max_tokens": max_tokens,
                "withdraw_tendency_result": round(withdraw_tendency, 6),
                "withdraw_tendency_stored": round(post["withdraw_tendency"], 6),
                "withdraw_penalty": round(withdraw_penalty, 6) if withdraw_penalty is not None else None,
                "tone_bias_pre": round(pre["tone_bias"], 6),
                "e_bg_pre": round(pre["e_bg"], 6) if pre["e_bg"] else None,
                "E_pre": round(pre["E"], 6), "T_pre": round(pre["T"], 6),
                "N_pre": round(pre["N"], 6), "M_pre": round(pre["M"], 6),
                "E_post": round(post["E"], 6), "T_post": round(post["T"], 6),
                "N_post": round(post["N"], 6), "M_post": round(post["M"], 6),
                "tone_bias_post": round(post["tone_bias"], 6),
                "ep_count_pre": pre["ep_count"], "ep_count_post": post["ep_count"],
                "last_stated_pre": pre["last_stated"], "last_stated_post": post["last_stated"],
                "llm_called": llm_called,
            })

        except Exception as e:
            import traceback
            print(f"  !!! EXCEPTION round {rnd}: {e}")
            traceback.print_exc()
            records.append({"round": rnd, "phase": phase, "input": user_input, "error": str(e), "reply": f"[ERROR: {e}]"})
            break

    # ── Summary ─────────────────────────────────────────────────────
    print(f"\n{'='*150}")
    print("FINAL SUMMARY")
    print(f"{'='*150}")

    valid = [r for r in records if "error" not in r]
    tiers = [r["mode_idx"] for r in valid]
    dist = Counter(tiers)

    print(f"\nTier distribution ({len(valid)} rounds):")
    for t in sorted(dist):
        print(f"  tier {t:>2d} ({names.get(t, '?'):>8s}): {dist[t]:>3d} ({dist[t]/len(valid)*100:>5.1f}%)")

    non_silent = [r for r in valid if r["mode_idx"] >= 1]
    llm_calls = [r for r in valid if r["llm_called"]]
    silent_rounds = [r for r in valid if r["mode_idx"] == 0]

    print(f"\nPath statistics:")
    print(f"  Non-silent (mode_idx>=1): {len(non_silent)}/{len(valid)}")
    print(f"  Silent (mode_idx==0): {len(silent_rounds)}/{len(valid)}")
    print(f"  LLM called: {len(llm_calls)}/{len(valid)}")
    distinct_valid = len(set(t for t in tiers if t >= 0))
    print(f"  Distinct valid tiers: {distinct_valid}")

    # Withdraw tendency curve
    print(f"\nWithdraw tendency curve:")
    for r in valid:
        wt = r.get("withdraw_tendency_result", 0)
        bar = "█" * int(wt * 40)
        marker = ""
        if r["mode_idx"] == 0:
            marker = " [SILENT]"
        print(f"  r{r['round']:02d} [{r['phase']:>12s}] w={wt:.4f} {bar}{marker}")

    # Reply length distribution
    lens = [r["reply_len"] for r in valid]
    print(f"\nReply length: min={min(lens)} avg={sum(lens)/len(lens):.0f} max={max(lens)}")

    # Emotional arc
    print(f"\nEmotional arc (reply chars per round):")
    for r in valid:
        marker = ""
        if r["mode_idx"] == 0:
            marker = " [SILENT]"
        wt = r.get("withdraw_tendency_result", 0)
        print(f"  r{r['round']:02d} [{r['phase']:>12s}] {r['reply_len']:>4d}ch mode={r['mode_idx']:>2d} w={wt:.4f}{marker} {repr(r['reply'][:80])}")

    # Hash chain
    chain_path = os.path.join(_ENGINE_DIR, "hash_chain_v2.log")
    chain = []
    with open(chain_path) as f:
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
        "run": "real-dialogue-30round-v4-withdraw",
        "timestamp": int(time.time()),
        "sigmoid": {"k": em._K_SAT, "E0": em._E0_SAT},
        "records": records,
        "summary": {
            "n_rounds": len(valid),
            "tier_distribution": {str(k): v for k, v in dist.items()},
            "non_silent_count": len(non_silent),
            "silent_count": len(silent_rounds),
            "llm_called_count": len(llm_calls),
            "distinct_tiers": distinct_valid,
            "reply_len": {"min": min(lens), "avg": round(sum(lens)/len(lens), 1), "max": max(lens)},
            "hash_chain": {"records": len(chain), "broken": broken},
        },
    }
    out_path = os.path.join(_ENGINE_DIR, "active_memory", "behavior_30round_withdraw_v4.json")
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    run()
