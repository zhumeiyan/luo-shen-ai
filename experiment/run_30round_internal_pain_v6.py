#!/usr/bin/env python3
"""
30-round real-dialogue observation v6 — internal pain (low energy + behavior rigidity).

Arc:
- Phase A (1-8): Normal chat, energy recovers slightly, low pain
- Phase B (9-18): User negative/stress, energy depletes, pain rises
- Phase C (19-24): Silence, low energy persists, pain stays high
- Phase D (25-30): Gentle recovery, energy recovers, pain falls

Records per round: internal_pain, low_energy_signal, rigidity_signal, response_pre, tier, reply.
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

# 30-round dialog arc
DIALOG = [
    # === Phase A: normal chat (1-8) ===
    "洛神你好",
    "今天天气不错",
    "我刚吃完午饭",
    "你在做什么呢",
    "我最近挺好的",
    "嗯嗯",
    "好的",
    "你今天心情怎么样",

    # === Phase B: negative emotions / stress (9-18) ===
    "其实我今天有点难过",
    "工作上的事情让我压力好大",
    "感觉好累好疲惫",
    "心里很烦躁",
    "焦虑得喘不过气",
    "觉得人生好迷茫",
    "内心很空虚压抑",
    "痛苦的感觉一直缠着我",
    "好委屈好无助",
    "我快崩溃了",

    # === Phase C: silence / no input (19-24) ===
    "",
    "",
    "",
    "",
    "",
    "",

    # === Phase D: gentle recovery (25-30) ===
    "谢谢你的陪伴",
    "现在感觉好点了",
    "你的温柔让我安心",
    "我们慢慢聊吧",
    "开心一点了",
    "晚安洛神",
]


def reset_memory_clean():
    """Reset to clean state, keep hash chain intact."""
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
    m['self_model']['internal_pain'] = 0.0
    m['self_model']['low_energy_signal'] = 0.0
    m['self_model']['rigidity_signal'] = 0.0
    m['self_model']['_withdraw_logit'] = 0.0
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
    internal_pain = mem.get("self_model", {}).get("internal_pain", 0.0)
    low_energy = mem.get("self_model", {}).get("low_energy_signal", 0.0)
    rigidity = mem.get("self_model", {}).get("rigidity_signal", 0.0)
    energy = climate.get("energy", float("nan"))

    return {
        "E": climate.get("emotion_intensity", float("nan")),
        "T": climate.get("tension", float("nan")),
        "N": climate.get("energy", float("nan")),
        "M": climate.get("memory_pressure", float("nan")),
        "energy": float(energy),
        "tone_bias": float(emr.get("tone_bias", 0.0)) if emr else 0.0,
        "arousal_bias": float(emr.get("arousal_bias", 0.0)) if emr else 0.0,
        "e_bg": float(emr.get("background", {}).get("e_bg", 0.0)) if emr and emr.get("background") else None,
        "ep_count": ep_cnt,
        "last_stated": last_stated,
        "internal_pain": float(internal_pain) if internal_pain is not None else 0.0,
        "low_energy_signal": float(low_energy) if low_energy is not None else 0.0,
        "rigidity_signal": float(rigidity) if rigidity is not None else 0.0,
    }


def run():
    records = []
    names = {0: "silent", 1: "brief", 2: "short", 3: "normal", 4: "engaged"}

    print("=" * 170)
    print("  30-Round Real Dialogue Observation v6 — internal pain (low energy + behavior rigidity)")
    print("=" * 170)

    # Reset to clean state
    reset_memory_clean()

    # Warm up pain series so computation starts immediately
    living_engine._warm_up_pain_series(205)

    # Verify initial state
    snap0 = get_snapshot()
    print(f"\nInitial state: energy={snap0['energy']:.4f}, ep_count={snap0['ep_count']}, internal_pain={snap0['internal_pain']:.6f}")
    print(f"Pain series warmed up: 205 entries")
    print()

    for rnd, user_input in enumerate(DIALOG, 1):
        if rnd <= 8:
            phase = "A(normal)"
        elif rnd <= 18:
            phase = "B(negative)"
        elif rnd <= 24:
            phase = "C(silence)"
        else:
            phase = "D(recovery)"

        display_input = "(silence)" if not user_input else repr(user_input)
        print(f"\n{'='*170}")
        print(f"  Round {rnd}/30 [{phase}]  USER: {display_input}")
        print(f"{'='*170}")

        # PRE-CALL SNAPSHOT
        pre = get_snapshot()
        print(f"    pre: energy={pre['energy']:+.4f} T={pre['T']:+.4f} N(pre-N/A) M={pre['M']:.3f} | tb={pre['tone_bias']:+.4f} ab={pre['arousal_bias']:+.4f} ep={pre['ep_count']}")
        print(f"    pre: pain={pre['internal_pain']:.6f} low_e={pre['low_energy_signal']:.4f} rig={pre['rigidity_signal']:.4f} | last_stated={repr(pre['last_stated'])}")

        # CALL
        try:
            t0 = time.time()
            result = living_engine.generate_response(
                user_input,
                source="real_dialogue_test_v6_internal_pain",
                source_id="user_A",
                extract_facts=False,
            )
            elapsed = time.time() - t0

            reply = result.get("reply", "")
            behavior = result.get("behavior", None)
            withdraw_tendency = result.get("withdraw_tendency", 0.0)
            internal_pain = result.get("internal_pain", 0.0)
            llm_called = result.get("llm_called", False)

            mode_idx = behavior.get("mode_idx", -1) if behavior else -1
            response_mode = behavior.get("response_mode", "no_behavior") if behavior else "no_behavior"
            response_tendency = behavior.get("response_tendency", 0.5) if behavior else 0.5
            max_tokens = behavior.get("max_tokens", -1) if behavior else -1
            pain_penalty = behavior.get("pain_penalty", None) if behavior else None
            withdraw_penalty = behavior.get("withdraw_penalty", None) if behavior else None

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
            print(f"    behavior: mode={mode_idx}({names.get(mode_idx,'?')}) rt={response_tendency:.4f} rsp={rsp_pre:+.4f} max_tok={max_tokens}")
            print(f"    pain: {internal_pain:.6f} low_e={post['low_energy_signal']:.4f} rig={post['rigidity_signal']:.4f} (penalty={pain_penalty if pain_penalty else 0:.4f})")
            print(f"    energy: {post['energy']:+.4f}(Δ={post['energy']-pre['energy']:+.4f}) | withdraw={withdraw_tendency:.6f} pen={withdraw_penalty if withdraw_penalty else 0:.4f}")
            print(f"    post: pain_stored={post['internal_pain']:.6f} | llm={llm_called}")
            if post['last_stated'] != pre['last_stated']:
                print(f"    *** last_stated CHANGED: {repr(pre['last_stated'])} -> {repr(post['last_stated'])} ***")

            records.append({
                "round": rnd, "phase": phase,
                "input": user_input, "reply": reply, "reply_len": len(reply),
                "elapsed_s": round(elapsed, 2),
                "mode_idx": mode_idx, "response_mode": response_mode,
                "response_tendency": round(response_tendency, 6),
                "response_pre": round(rsp_pre, 6),
                "max_tokens": max_tokens,
                "internal_pain_result": round(internal_pain, 6),
                "internal_pain_stored": round(post["internal_pain"], 6),
                "internal_pain_delta": round(post["internal_pain"] - pre["internal_pain"], 6),
                "low_energy_signal_stored": round(post["low_energy_signal"], 6),
                "rigidity_signal_stored": round(post["rigidity_signal"], 6),
                "pain_penalty": round(pain_penalty, 6) if pain_penalty is not None else None,
                "energy_pre": round(pre["energy"], 6),
                "energy_post": round(post["energy"], 6),
                "energy_delta": round(post["energy"] - pre["energy"], 6),
                "withdraw_stored": round(post.get("withdraw_tendency", 0.0), 6),
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
    print(f"\n{'='*170}")
    print("FINAL SUMMARY")
    print(f"{'='*170}")

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

    # Internal pain curve
    print(f"\nInternal pain curve (from internal state, NOT keyword):")
    for r in valid:
        p = r.get("internal_pain_stored", 0)
        bar = "▓" * int(p * 40)
        le = r.get("low_energy_signal_stored", 0)
        rig = r.get("rigidity_signal_stored", 0)
        e = r.get("energy_post", 0.5)
        marker = ""
        if r["mode_idx"] == 0:
            marker = " [SILENT]"
        ebar = "░" * int(e * 20)
        print(f"  r{r['round']:02d} [{r['phase']:>11s}] p={p:.4f} {bar}  le={le:.3f} rig={rig:.3f} E={e:.3f}{ebar}{marker}")

    # Phase averages
    print(f"\nPhase averages:")
    for ph in ["A(normal)", "B(negative)", "C(silence)", "D(recovery)"]:
        phase_recs = [r for r in valid if r["phase"] == ph]
        if phase_recs:
            avg_pain = sum(r["internal_pain_stored"] for r in phase_recs) / len(phase_recs)
            avg_low_e = sum(r["low_energy_signal_stored"] for r in phase_recs) / len(phase_recs)
            avg_rig = sum(r["rigidity_signal_stored"] for r in phase_recs) / len(phase_recs)
            avg_energy = sum(r["energy_post"] for r in phase_recs) / len(phase_recs)
            avg_reply = sum(r["reply_len"] for r in phase_recs) / len(phase_recs)
            tiers_in_phase = [r["mode_idx"] for r in phase_recs]
            tier_min = min(tiers_in_phase)
            tier_max = max(tiers_in_phase)
            print(f"  {ph:>11s}: pain={avg_pain:.4f} low_e={avg_low_e:.4f} rig={avg_rig:.4f} E={avg_energy:.3f} reply={avg_reply:.0f}ch tier=[{tier_min}-{tier_max}]")

    # Pain from internal state verification
    print(f"\nPain source verification (internal state, NOT keyword):")
    for r in valid[:5] + valid[14:19]:
        p = r.get("internal_pain_stored", 0)
        le = r.get("low_energy_signal_stored", 0)
        rig = r.get("rigidity_signal_stored", 0)
        # Verify: pain = sigmoid(3*(0.6*le + 0.4*rig) - 1.5)
        import math
        expected_x = 0.6 * le + 0.4 * rig
        expected_pain = 1.0 / (1.0 + math.exp(-(3.0 * expected_x - 1.5)))
        print(f"  r{r['round']:02d}: pain={p:.6f}, expected_from_sigmoid={expected_pain:.6f}, match={abs(p-expected_pain)<0.001}")

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
        "run": "real-dialogue-30round-v6-internal-pain",
        "timestamp": int(time.time()),
        "records": records,
        "summary": {
            "n_rounds": len(valid),
            "tier_distribution": {str(k): v for k, v in dist.items()},
            "non_silent_count": len(non_silent),
            "silent_count": len(silent_rounds),
            "llm_called_count": len(llm_calls),
            "distinct_tiers": distinct_valid,
            "hash_chain": {"records": len(chain), "broken": broken},
        },
    }
    out_path = os.path.join(_ENGINE_DIR, "active_memory", "behavior_30round_internal_pain_v6.json")
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    run()
