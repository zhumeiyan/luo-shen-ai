"""
自我反思记忆 P/N 验证实验

设计说明：这是状态到文本的映射，不是真正的自我反思。
给定相同的 NEUTRAL 输入，P 组（正历史）和 N 组（负历史）的行为应产生可测量的差异，
且该差异必须通过自我反思记忆读取实现，而不是 rp_ema/当前输入。

实验流程：
  1. P 组：正向输入 500 tick → 构建正历史
  2. N 组：负向输入 500 tick → 构建负历史
  3. 两组随后各给 20 tick 中性输入 → 对比行为差异
  4. 记录自我反思记忆文本、episodic_memory 内容、memory emergence、行为参数
"""

import sys, os, json, csv

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# 引入 LLM mock（与 run_sdepth_4group.py 一致）
import llm_interface
llm_interface.call_llm = lambda d, m: ""

NEG_WORDS = {"烦","累","痛","哭","不想","没用","失去","死","孤独","绝望",
             "无聊","迷茫","压力","崩溃","抑郁","苦","难","没意思","难受",
             "失望","焦虑","噩梦","伤心","沉默","逃避","失败","挫败"}
POS_WORDS = {"开心","快乐","幸福","满足","笑容","温暖","美好","希望","喜欢",
             "阳光","感谢","不错","挺好","轻快","棒","真好",
             "舒适","愉快","乐观","期待","满意","幸运"}

def _rule_sentiment(t):
    n = sum(1 for w in NEG_WORDS if w in t)
    p = sum(1 for w in POS_WORDS if w in t)
    if n == 0 and p == 0:
        return 0.0, 0.45
    tot = n + p
    v = (p - n) / tot if tot > 0 else 0.0
    return v, min(0.9, 0.45 + (tot / max(1, len(t))) * 8)

import input_pressure
input_pressure._call_llm_sentiment = _rule_sentiment

from living_engine import (
    _apply_input_pressure, _save_json_atomic, _load_json,
    _compute_memory_emergence, _update_luoshen_coupled,
    _encode_episodic_memory, _select_behavior,
)
from run_r_experiment import (
    POSITIVE_INPUTS, NEGATIVE_INPUTS, NEUTRAL_INPUTS,
    SYNTHETIC_ENV, reset_memory, get_snapshot,
)

OUT_DIR = os.path.join(WORKSPACE, "experiment", "self_reflection_pn")
os.makedirs(OUT_DIR, exist_ok=True)


def run_group(gname, hist_inputs, pre_ticks, post_inputs, post_ticks):
    """
    构建 pre_ticks 历史后，运行 post_ticks 中性输入。
    history_end（第 500 tick）+ 每个 post tick 全部记录。
    """
    state_path = os.path.join(OUT_DIR, f"memory_{gname}.json")
    reset_memory(state_path)
    memory = _load_json(state_path)

    rows = []

    def _step(tick_id, inp, phase_label):
        _apply_input_pressure(memory, inp)
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (tick_id % 86400) / 86400.0
        _update_luoshen_coupled(memory, env, tick_id=tick_id)
        _encode_episodic_memory(memory)
        em = _compute_memory_emergence(memory)
        behavior = _select_behavior(memory, em)

        # 记录本轮 max_tokens 到滚动历史（供下一 tick 自我反思读取）
        _rt = memory.get("self_model", {}).setdefault("_recent_tokens", [])
        _rt.append(behavior.get("max_tokens", 80))
        if len(_rt) > 10:
            _rt.pop(0)

        snap = get_snapshot(memory)

        # 自我反思记忆
        self_refl = memory.get("self_model", {}).get("self_reflection_latest", "")
        # 检查是否有 self_reflection 类型的 episodic memory
        episodic = memory.get("episodic_memory", [])
        refl_mems = [e for e in episodic if e.get("kind") == "self_reflection"]
        has_refl_mem = len(refl_mems) > 0
        latest_refl_mem = refl_mems[-1] if refl_mems else {}
        refl_meta = latest_refl_mem.get("reflection_meta", {})
        refl_e_s = latest_refl_mem.get("e_s", 0.0)
        refl_t_s = latest_refl_mem.get("t_s", 0.0)

        row = {
            "tick": tick_id,
            "group": gname,
            "phase": phase_label,
            "input_text": inp[:12],
            "self_reflection": self_refl,
            "has_self_refl_mem": has_refl_mem,
            "refl_openness": refl_meta.get("openness", ""),
            "refl_emo_trend": refl_meta.get("emo_trend", ""),
            "refl_pressure": refl_meta.get("pressure", ""),
            "refl_e_s": refl_e_s,
            "refl_t_s": refl_t_s,
            "em_tone_bias": em.get("tone_bias", 0),
            "em_arousal_bias": em.get("arousal_bias", 0),
            "em_narrative_potential": em.get("narrative_potential", 0),
            "resp_tendency": behavior.get("response_tendency", 0),
            "max_tokens": behavior.get("max_tokens", 0),
            "mode": behavior.get("response_mode", ""),
            "rp_ema": snap.get("rp_ema", 0),
            "s_depth": snap.get("s_depth", 0),
            "E": snap.get("E", 0), "T": snap.get("T", 0), "N": snap.get("N", 0),
        }
        _save_json_atomic(state_path, memory)
        return row

    # Phase 1: History
    for i in range(1, pre_ticks + 1):
        inp = hist_inputs[(i - 1) % len(hist_inputs)]
        row = _step(i, inp, "history")
        if i in (1, 10, 50, 100, 200, 300, 400, 500):
            rows.append(row)

    # Phase 2: Post (same neutral input for both groups)
    last_row = None
    for j in range(1, post_ticks + 1):
        tick_id = pre_ticks + j
        inp = post_inputs[(j - 1) % len(post_inputs)]
        row = _step(tick_id, inp, "neutral_post")
        rows.append(row)
        last_row = row

    return rows, last_row


def main():
    print("=" * 70)
    print("Self-Reflection Memory P/N Validation Experiment")
    print("声明：这是状态到文本的映射，不是真正的自我反思。")
    print("=" * 70)

    # Group P: positive history → neutral
    print("\n--- Group P: positive history (500t) → neutral (20t) ---")
    rows_P, last_P = run_group(
        "P", POSITIVE_INPUTS, pre_ticks=500,
        post_inputs=NEUTRAL_INPUTS, post_ticks=20,
    )

    # Group N: negative history → neutral
    print("\n--- Group N: negative history (500t) → neutral (20t) ---")
    rows_N, last_N = run_group(
        "N", NEGATIVE_INPUTS, pre_ticks=500,
        post_inputs=NEUTRAL_INPUTS, post_ticks=20,
    )

    # Save CSV
    out_path = os.path.join(OUT_DIR, "results.csv")
    all_rows = rows_P + rows_N
    fieldnames = list(all_rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"\nSaved: {out_path}")

    # ---------- COMPARISON REPORT ----------
    print("\n" + "=" * 70)
    print("COMPARISON: P (positive history) vs N (negative history)")
    print("          Same input: NEUTRAL ('在吗', '嗯', '好', '行', '氧')")
    print("声明：这是状态到文本的映射，不是真正的自我反思。")
    print("=" * 70)

    # History-end comparison
    hP = rows_P[-1]  # last history row
    hN = rows_N[-1]
    print(f"\n[History End — tick 500 — before neutral input]")
    print(f"  {'Field':<25} {'P':<25} {'N':<25}")
    print(f"  {'-'*75}")
    for k in ["self_reflection", "mode", "max_tokens", "rp_ema", "s_depth",
              "em_tone_bias", "em_arousal_bias", "refl_openness", "refl_emo_trend"]:
        vP = hP.get(k, "")
        vN = hN.get(k, "")
        if isinstance(vP, float):
            print(f"  {k:<25} {vP:<25.4f} {vN:<25.4f}")
        else:
            sP = str(vP)[:24]
            sN = str(vN)[:24]
            print(f"  {k:<25} {sP:<25} {sN:<25}")

    # Post comparison: all 20 neutral ticks
    print(f"\n[Neutral Post — 20 ticks each — per-tick comparison]")
    print(f"  {'tick':<6} {'P_mode':<10} {'P_max_tok':<10} {'P_refl':<20} | "
          f"{'N_mode':<10} {'N_max_tok':<10} {'N_refl':<20}")
    print(f"  {'-'*100}")
    for rP, rN in zip(rows_P[len(rows_P)-20:], rows_N[len(rows_N)-20:]):
        t = rP["tick"]
        reflP = str(rP["self_reflection"])[:18]
        reflN = str(rN["self_reflection"])[:18]
        print(f"  {t:<6} {rP['mode']:<10} {rP['max_tokens']:<10} {reflP:<20} | "
              f"{rN['mode']:<10} {rN['max_tokens']:<10} {reflN:<20}")

    # Last post tick summary
    print(f"\n[Final Neutral Tick = tick 520]")
    print(f"  {'Field':<25} {'P':<25} {'N':<25} {'Diff (P-N)':<15}")
    print(f"  {'-'*90}")
    for k in ["mode", "max_tokens", "resp_tendency", "em_tone_bias", "em_arousal_bias",
              "rp_ema", "s_depth", "refl_openness", "refl_emo_trend", "refl_pressure"]:
        vP = last_P.get(k, "")
        vN = last_N.get(k, "")
        if isinstance(vP, float):
            diff = vP - vN
            print(f"  {k:<25} {vP:<25.4f} {vN:<25.4f} {diff:<+15.4f}")
        else:
            sP = str(vP)[:24]
            sN = str(vN)[:24]
            print(f"  {k:<25} {sP:<25} {sN:<25} {'':<15}")

    # Verdict
    same_input = True  # both groups receive NEUTRAL input
    modes_differ = last_P["mode"] != last_N["mode"]
    tokens_differ = abs(last_P["max_tokens"] - last_N["max_tokens"]) > 10
    reflections_differ = last_P["self_reflection"] != last_N["self_reflection"]

    print(f"\n[Verdict]")
    print(f"  Same input applied to both groups: YES (NEUTRAL)")
    print(f"  Self-reflection texts differ: {'YES' if reflections_differ else 'NO'}")
    print(f"  Response mode differs: {'YES' if modes_differ else 'NO'}")
    print(f"  max_tokens differ by >10: {'YES' if tokens_differ else 'NO'} "
          f"(P={last_P['max_tokens']}, N={last_N['max_tokens']})")
    print(f"\n  声明：这是状态到文本的映射，不是真正的自我反思。")
    print(f"\nDONE.")


if __name__ == "__main__":
    main()
