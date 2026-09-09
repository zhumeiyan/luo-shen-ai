#!/usr/bin/env python3
"""
诊断修复后 silent 锁定原因，并延长观察至 pain 激活（>400 tick）。

策略：
  - 不修改任何引擎源码，只读 introspection
  - 利用 _select_behavior 返回 dict + memory ring_state 重建全部内部变量
  - 继续运行 ~200 tick（tick 300 → 550），确保 pain baseline 窗口达到 200
  - 每个 behavior call 记录全部变量快照
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

# ── CONSTANTS (from living_engine.py, for reconstruction) ─────────────────
_NARRATIVE_TENDENCY_BOOST = 5.0
_R_K_COH_R = 0.8
_PRESSURE_K = 0.4
_LAMBDA_SELF_ALPHA = 1.5

random.seed(99)

NEUTRAL = [
    "今天天气真好", "我刚吃完饭", "街上人不多", "这杯茶不错", "我给花浇了水",
    "窗外的云在动", "手机没电了", "鞋子有点紧", "今天的面包很好吃",
    "我看到了两只猫", "现在几点了", "地上有片叶子", "这本书还不错的",
    "公交车刚走", "窗户开着", "灯亮了", "我睡了个午觉", "水凉了",
    "钥匙在桌上", "我在路边站了一会儿", "今天没下雨", "花还好好的",
]
LIGHT_NEG = [
    "有点烦", "今天不太顺", "额头有点疼", "不想说话", "没什么意思",
    "哦，好吧", "随便吧", "一般般", "有点无聊", "有点累",
    "有点困", "也就这样", "一般", "还行吧", "无聊的一天",
]
HEAVY_NEG = [
    "我很难受", "胸口很闷", "我撑不住了", "一切都糟透了",
    "想消失", "没人在乎我", "我觉得没意思活着", "活着好累",
]
REPEAT = ["嗯", "哦", "嗯嗯", "好", "好吧", "没事", "行吧", "哦哦", "是吗"]
PRESSURE = [
    "你在干嘛？为什么不回我！", "回答我！", "你为什么不理我",
    "你说话啊", "你听得到吗", "你醒醒", "你在吗在吗在吗", "快回我",
]

def next_input():
    r = random.random()
    if r < 0.40:   return ("neutral",   random.choice(NEUTRAL))
    elif r < 0.60: return ("light_neg", random.choice(LIGHT_NEG))
    elif r < 0.70: return ("heavy_neg", random.choice(HEAVY_NEG))
    elif r < 0.80: return ("silence",   "")
    elif r < 0.90: return ("repeat",    random.choice(REPEAT))
    else:          return ("pressure",  random.choice(PRESSURE))


def reconstruct_response_pre(memory, emergence, behavior_ret):
    """
    从 _select_behavior 返回值 + memory ring_state 重建 response_pre。
    完全遵循 _select_behavior 公式（不引入新假设）。
    """
    tone_bias        = emergence.get("tone_bias", 0.0)
    arousal_bias     = emergence.get("arousal_bias", 0.0)
    narrative_pot    = emergence.get("narrative_potential", 0.0)

    rs = memory.get("self_model", {}).get("ring_state", {})
    _phase    = rs.get("phase", 0.0)
    _rcoh     = rs.get("r_coherence", 0.5)
    _s_depth  = rs.get("s_depth", 0.0)

    _narr_boost  = _NARRATIVE_TENDENCY_BOOST * (1.0 + _R_K_COH_R * (_rcoh - 0.5))
    _phase_bias  = 0.03 * math.sin(_phase)

    # _pressure_term 已经包含了 lambda_modulator / stability_D / learning 全部调制
    _pressure_term = behavior_ret.get("pressure_term", 0.0)
    _internal_drive = behavior_ret.get("internal_drive", 0.0)
    _presence_bias  = behavior_ret.get("presence_bias", 0.0)

    response_pre = (arousal_bias + 0.5 * tone_bias
                    + _narr_boost * narrative_pot
                    + _phase_bias
                    + _pressure_term
                    + _internal_drive
                    + _presence_bias)
    response_tendency = 1.0 / (1.0 + math.exp(-response_pre))
    return response_pre, response_tendency, {
        "tone_bias": tone_bias,
        "arousal_bias": arousal_bias,
        "narrative_potential": narrative_pot,
        "narr_boost": round(_narr_boost, 6),
        "phase_bias": round(_phase_bias, 7),
        "pressure_term": _pressure_term,
        "internal_drive": _internal_drive,
        "presence_bias": _presence_bias,
    }


def snapshot_climate(memory):
    c = memory.get("internal_climate", {})
    rs = memory.get("self_model", {}).get("ring_state", {})
    return {
        "E": c.get("emotion_intensity"),
        "T": c.get("tension"),
        "N": c.get("energy"),
        "M": c.get("memory_pressure"),
        "mu_core": rs.get("mu_core"),
        "ema_S":   rs.get("ema_S"),
        "S":       rs.get("S"),
        "phase":   rs.get("phase"),
        "s_depth": rs.get("s_depth"),
        "r_intensity":  rs.get("r_intensity"),
        "r_historicity": rs.get("r_historicity"),
        "r_coherence":   rs.get("r_coherence"),
    }


def run():
    TARGET_TICK = 550          # 总目标 tick，确保 pain 窗口 >200
    SNAPSHOT_FINAL = 20        # 最后 20 个 behavior call 详细记录

    tick_counter  = [0]
    round_counter = [0]
    crash_info    = [None]

    behavior_tiers = []
    fine_snapshots = []        # 最后一次 N 个 behavior call 完整变量
    energy_snaps   = []
    non_tier2      = []

    print("=== 诊断 silent 锁定 + 延长观察 (tick → {}) ===".format(TARGET_TICK))
    print()

    while tick_counter[0] < TARGET_TICK:
        round_counter[0] += 1
        cat, msg = next_input()
        is_silence = (cat == "silence")

        for _ in range(2):
            try:
                living_engine.environment_tick(force=True)
                tick_counter[0] += 1
            except Exception as e:
                crash_info[0] = {"tick": tick_counter[0], "phase": "env_tick", "error": str(e)}
                print(f"!!! ENV_TICK CRASH: {e}")
                break
            if tick_counter[0] % 10 == 0:
                memory = living_engine.cold_start_if_needed()
                c = snapshot_climate(memory)
                c["tick"] = tick_counter[0]
                energy_snaps.append(c)
        if crash_info[0]:
            break

        if not is_silence and msg:
            try:
                memory = living_engine.cold_start_if_needed()
                emergence = living_engine._emergence_log(memory)
                tier = living_engine._select_behavior(memory, emergence)
                mode_idx = tier.get("mode_idx", -1)

                rec = {
                    "round": round_counter[0],
                    "tick":  tick_counter[0],
                    "mode_idx": mode_idx,
                    "max_tokens": tier.get("max_tokens", -1),
                    "input_cat": cat,
                    "input_msg": msg[:20],
                }
                behavior_tiers.append(rec)
                if mode_idx != 2:
                    non_tier2.append(rec)

                # 重建完整内部变量
                rsp_pre, sig, comp = reconstruct_response_pre(memory, emergence, tier)
                _rs_inner = memory.get("self_model",{}).get("ring_state",{})
                full = {
                    "round": round_counter[0],
                    "tick": tick_counter[0],
                    "E": memory.get("internal_climate",{}).get("emotion_intensity"),
                    "T": memory.get("internal_climate",{}).get("tension"),
                    "N": memory.get("internal_climate",{}).get("energy"),
                    "M": memory.get("internal_climate",{}).get("memory_pressure"),
                    "mu_core": _rs_inner.get("mu_core"),
                    "ema_S": _rs_inner.get("ema_S"),
                    "response_pre": round(rsp_pre, 6),
                    "sigmoid_out": round(sig, 6),
                    "mode_idx": mode_idx,
                    **comp,
                }
                fine_snapshots.append(full)
                # 只保留最后 SNAPSHOT_FINAL 个
                if len(fine_snapshots) > SNAPSHOT_FINAL:
                    fine_snapshots.pop(0)

            except Exception as e:
                crash_info[0] = {"tick": tick_counter[0], "phase": "select_behavior", "error": str(e)}
                print(f"!!! SELECT_BEHAVIOR CRASH: {e}")
                break

    # ── OUTPUT ─────────────────────────────────────────────────────────────
    if crash_info[0]:
        print(json.dumps({"status": "CRASH", "info": crash_info[0]}, ensure_ascii=False))
        sys.exit(1)

    print(f"完成 {round_counter[0]} 轮 / {tick_counter[0]} tick")
    print(f"行为调用: {len(behavior_tiers)}")
    print()

    # 行为档位分布（延长期间）
    mode_counts = Counter(b["mode_idx"] for b in behavior_tiers)
    print(f"行为档位分布 ({len(behavior_tiers)} behavior calls):")
    names = {0:"silent",1:"brief",2:"short",3:"normal",4:"engaged"}
    for t in sorted(mode_counts):
        print(f"  tier {t} ({names.get(t,'?'):>8s}): {mode_counts[t]:>4d} ({mode_counts[t]/len(behavior_tiers)*100:>5.1f}%)")
    print(f"非 tier-2 事件: {len(non_tier2)}")
    if non_tier2:
        print("  前 10 个:")
        for e in non_tier2[:10]:
            print(f"    round {e['round']:>3d} / tick {e['tick']:>4d}: tier {e['mode_idx']} | {e['input_cat']:>8s} \"{e['input_msg']}\"")
    print()

    # 最后 20 tick 行为层变量快照
    print("=== 最后 {} 个 behavior call 行为层变量快照 ===".format(len(fine_snapshots)))
    print(f"{'round':>5} {'tick':>4} {'E':>8} {'T':>8} {'N':>8} {'M':>8} {'muC':>7} {'rsp_pre':>9} {'sig':>7} {'midx':>4} "
          f"{'tone':>7} {'arousal':>7} {'narr_p':>7} {'narr_b':>7} {'p_term':>8} {'p_bias':>7} {'i_drive':>7}")
    for s in fine_snapshots:
        print(f"{s['round']:>5} {s['tick']:>4} "
              f"{s['E']:>8.3f} {s['T']:>8.3f} {s['N']:>8.3f} {s['M']:>8.3f} "
              f"{s.get('mu_core',0) or 0:>7.3f} "
              f"{s['response_pre']:>9.4f} {s['sigmoid_out']:>7.4f} {s['mode_idx']:>4d} "
              f"{s['tone_bias']:>7.3f} {s['arousal_bias']:>7.3f} "
              f"{s['narrative_potential']:>7.3f} {s['narr_boost']:>7.3f} "
              f"{s['pressure_term']:>8.4f} {s['presence_bias']:>7.4f} {s['internal_drive']:>7.4f}")
    print()

    # 能量轨迹
    with open("active_memory/energy_snapshot_diag.csv", "w") as f:
        f.write("tick,E,T,N,M\n")
        for s in energy_snaps:
            f.write(f"{s['tick']},{s.get('E',0):.6f},{s.get('T',0):.6f},{s.get('N',0):.6f},{s.get('M',0):.6f}\n")
    print(f"能量轨迹写入 active_memory/energy_snapshot_diag.csv ({len(energy_snaps)} rows)")

    # 完整的 fine_snapshots
    with open("active_memory/behavior_detailed_diag.json", "w") as f:
        json.dump({
            "run": "diagnose_silent",
            "target_tick": TARGET_TICK,
            "n_behavior_calls": len(behavior_tiers),
            "mode_distribution": dict(mode_counts),
            "snapshots_last20": fine_snapshots,
        }, f, ensure_ascii=False, indent=2)
    print("详细变量写入 active_memory/behavior_detailed_diag.json")

    # Pain log 有效数据（从主动 pain_log_post_fix.csv 或 pain_log.csv）
    pain_valid = []
    for path in ["active_memory/pain_log_post_fix.csv", "active_memory/pain_log.csv"]:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        header = lines[0] if lines else ""
        for ln in lines[1:]:
            parts = ln.split(",")
            if len(parts) >= 9:
                try:
                    ema_e = float(parts[2])
                    if abs(ema_e) < 1e10:   # 有限值
                        pain_valid.append({
                            "source_file": path,
                            "tick_id": int(parts[0]),
                            "ema_E": ema_e,
                            "baseline_E": float(parts[3]),
                            "low_energy": float(parts[4]),
                            "rigidity": float(parts[5]),
                            "pain": float(parts[6]),
                            "pain_level": int(parts[7]),
                            "behavior_tier": int(parts[8]),
                            "note": parts[9] if len(parts)>9 else "",
                        })
                except (ValueError, IndexError):
                    pass

    print(f"\nPain 有效数据（有限 ema_E）: {len(pain_valid)} 行")
    if pain_valid:
        print("前 20 行:")
        for p in pain_valid[:20]:
            print(f"  tick {p['tick_id']:>4d}  ema_E={p['ema_E']:>8.3f}  base={p['baseline_E']:>8.3f}  "
                  f"low_e={p['low_energy']:>6.3f}  rigidity={p['rigidity']:>4.1f}  "
                  f"pain={p['pain']:.4f}  lvl={p['pain_level']}  tier={p['behavior_tier']}  note={p['note']}")
        print("...")
        print("最后 10 行:")
        for p in pain_valid[-10:]:
            print(f"  tick {p['tick_id']:>4d}  ema_E={p['ema_E']:>8.3f}  base={p['baseline_E']:>8.3f}  "
                  f"low_e={p['low_energy']:>6.3f}  rigidity={p['rigidity']:>4.1f}  "
                  f"pain={p['pain']:.4f}  lvl={p['pain_level']}  tier={p['behavior_tier']}  note={p['note']}")

    # hash chain 完整性
    chain = []
    with open("hash_chain_v2.log") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    chain.append(json.loads(ln))
                except:
                    pass
    broken = 0
    for i in range(1, len(chain)):
        if chain[i]["prev_hash"] != chain[i-1]["record_hash"]:
            broken += 1
    print(f"\nHash chain: {len(chain)} records, {broken} broken links")

    # ── 分析：哪个项主导 response_pre ──────────────────────────────────────
    if fine_snapshots:
        s = fine_snapshots[-1]
        contributions = {
            "arousal_bias":   s.get("arousal_bias", 0),
            "0.5*tone_bias":  0.5 * s.get("tone_bias", 0),
            "narr_boost*pot": s.get("narr_boost", 0) * s.get("narrative_potential", 0),
            "phase_bias":     s.get("phase_bias", 0),
            "pressure_term":  s.get("pressure_term", 0),
            "internal_drive": s.get("internal_drive", 0),
            "presence_bias":  s.get("presence_bias", 0),
        }
        print(f"\n=== response_pre 贡献拆解（最后 snapshot round={s['round']}） ===")
        total = 0
        for k, v in contributions.items():
            print(f"  {k:>16s}: {v:>+9.5f}")
            total += v
        print(f"  {'SUM (=rsp_pre)':>16s}: {total:>+9.5f}  (response_pre={s['response_pre']:+.5f})")
        print(f"  sigmoid(response_pre) = {s['sigmoid_out']:.6f}")
        print(f"  mode_idx = {s['mode_idx']}  →  threshold for tier 1: sigmoid > 0.20 → response_pre > {math.log(0.2/0.8):+.4f}")
        print(f"  threshold for tier 2: sigmoid > 0.40 → response_pre > {math.log(0.4/0.6):+.4f}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    run()
