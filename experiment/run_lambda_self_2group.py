#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lambda-Self 自调节机制验证实验。

实验组：_LAMBDA_SELF_ALPHA = 1.5，单一正向输入 1000 tick。
对照组：_LAMBDA_SELF_ALPHA = 0.0（关闭调节），相同输入 1000 tick。

每 10 tick 记录：lambda_self、max_tokens、mode、rp_ema、s_depth、E/T/N/M、pressure_term。
判定标准：
  1. 实验组 max_tokens 方差 > 对照组
  2. 实验组 mode 切换次数 > 对照组
  3. lambda_self 上升后 10 tick 内 max_tokens 显著增加（因果证据）
  4. 对照组僵化/低方差
"""

import sys, os, json, csv, math

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
os.chdir(WORKSPACE)

# ── LLM mock ──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

# ── Sentiment mock（与 run_sdepth_4group.py 一致）──
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

import living_engine as le
from living_engine import (
    _apply_input_pressure, _save_json_atomic, _load_json,
    _compute_memory_emergence, _update_luoshen_coupled,
    _encode_episodic_memory,
)
from run_r_experiment import (
    POSITIVE_INPUTS, SYNTHETIC_ENV, reset_memory,
)

OUT_DIR = os.path.join(WORKSPACE, "experiment", "lambda_self_2group")
os.makedirs(OUT_DIR, exist_ok=True)


def get_snapshot(memory):
    """提取记录所需的状态快照"""
    rs = memory.get("self_model", {}).get("ring_state", {})
    ic = memory.get("internal_climate", {})
    return {
        "lambda_self": rs.get("lambda_self", 0.0),
        "rp_ema": rs.get("relational_pressure_ema", 0.0),
        "s_depth": rs.get("s_depth", 0.0),
        "E": ic.get("emotion_intensity", 0.5),
        "T": ic.get("tension", 0.0),
        "N": ic.get("energy", 0.5),
        "M": ic.get("memory_pressure", 0.3),
    }


def run_group(gname, alpha_val, total_ticks=1000):
    """运行一组实验，alpha_val 控制 _LAMBDA_SELF_ALPHA"""
    # 临时覆盖模块级常量
    le._LAMBDA_SELF_ALPHA = alpha_val

    state_path = os.path.join(OUT_DIR, f"memory_{gname}.json")
    reset_memory(state_path)
    memory = _load_json(state_path)

    rows = []

    for i in range(1, total_ticks + 1):
        inp = POSITIVE_INPUTS[(i - 1) % len(POSITIVE_INPUTS)]

        _apply_input_pressure(memory, inp)
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (i % 86400) / 86400.0
        _update_luoshen_coupled(memory, env, tick_id=i)
        _encode_episodic_memory(memory)
        em = _compute_memory_emergence(memory)
        behavior = le._select_behavior(memory, em)

        # 手动调用历史更新（因为不经过 _generate_response_impl）
        le._update_lambda_histories(memory, behavior["max_tokens"], behavior["pressure_ema"])

        snap = get_snapshot(memory)
        row = {
            "tick": i,
            "group": gname,
            "alpha": alpha_val,
            "self_reflection": le._compute_lambda_self(memory) if hasattr(le, '_compute_lambda_self') else snap["lambda_self"],
            "lambda_self": snap["lambda_self"],
            "max_tokens": behavior["max_tokens"],
            "mode": behavior["response_mode"],
            "resp_tendency": behavior["response_tendency"],
            "pressure_term": behavior.get("pressure_term", 0.0),
            "lambda_modulator": behavior.get("lambda_modulator", 1.0),
            "rp_ema": snap["rp_ema"],
            "s_depth": snap["s_depth"],
            "E": snap["E"], "T": snap["T"], "N": snap["N"], "M": snap["M"],
        }

        rows.append(row)
        _save_json_atomic(state_path, memory)

    return rows


def main():
    print("=" * 70)
    print("Lambda-Self 自调节机制验证")
    print("实验组 ALPHA=1.5 vs 对照组 ALPHA=0.0")
    print("=" * 70)

    # 实验组
    print("\n--- 运行实验组 (alpha=1.5) ---")
    rows_exp = run_group("EXP", alpha_val=1.5, total_ticks=1000)

    # 对照组
    print("\n--- 运行对照组 (alpha=0.0) ---")
    rows_ctrl = run_group("CTRL", alpha_val=0.0, total_ticks=1000)

    # Save CSV
    out_path = os.path.join(OUT_DIR, "results.csv")
    fieldnames = list(rows_exp[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows_exp + rows_ctrl:
            w.writerow(r)
    print(f"\nSaved: {out_path}")

    # ── 统计计算 ──
    def variance(vals):
        n = len(vals)
        if n < 2: return 0.0
        m = sum(vals) / n
        return sum((v - m) ** 2 for v in vals) / (n - 1)

    def mode_switches(modes):
        """统计 mode 切换次数（mode 字符串变化）"""
        s = 0
        for i in range(1, len(modes)):
            if modes[i] != modes[i - 1]:
                s += 1
        return s

    exp_tokens = [r["max_tokens"] for r in rows_exp]
    ctrl_tokens = [r["max_tokens"] for r in rows_ctrl]
    exp_modes = [r["mode"] for r in rows_exp]
    ctrl_modes = [r["mode"] for r in rows_ctrl]
    exp_lambda = [r["lambda_self"] for r in rows_exp]

    var_exp = variance(exp_tokens)
    var_ctrl = variance(ctrl_tokens)
    sw_exp = mode_switches(exp_modes)
    sw_ctrl = mode_switches(ctrl_modes)

    # lambda_self 因果证据
    causal_evidence = []
    for i in range(len(rows_exp) - 10):
        if i < 10: continue
        lam_now = rows_exp[i]["lambda_self"]
        lam_prev = rows_exp[i - 5]["lambda_self"]
        if lam_now > lam_prev + 0.02:  # lambda 显著上升
            tok_now = rows_exp[i]["max_tokens"]
            tok_after = rows_exp[i + 10]["max_tokens"]
            delta_tok = tok_after - tok_now
            if delta_tok > 20:
                causal_evidence.append((i, lam_prev, lam_now, tok_now, tok_after, delta_tok))

    print("\n" + "=" * 70)
    print("统计结果")
    print("=" * 70)
    print(f'\n{"指标":<30} {"实验组(ALPHA=1.5)":<20} {"对照组(ALPHA=0.0)":<20}')
    print("-" * 70)
    print(f'{"max_tokens 方差":<30} {var_exp:<20.4f} {var_ctrl:<20.4f}')
    print(f'{"max_tokens 均值":<30} {sum(exp_tokens)/len(exp_tokens):<20.4f} {sum(ctrl_tokens)/len(ctrl_tokens):<20.4f}')
    print(f'{"max_tokens 最小值":<30} {min(exp_tokens):<20} {min(ctrl_tokens):<20}')
    print(f'{"max_tokens 最大值":<30} {max(exp_tokens):<20} {max(ctrl_tokens):<20}')
    print(f'{"mode 切换次数":<30} {sw_exp:<20} {sw_ctrl:<20}')
    print(f'{"mode 分布(实验组)":<30} {dict((m, exp_modes.count(m)) for m in set(exp_modes))}')
    print(f'{"mode 分布(对照组)":<30} {dict((m, ctrl_modes.count(m)) for m in set(ctrl_modes))}')
    print(f'{"lambda_self 均值":<30} {sum(exp_lambda)/len(exp_lambda):<20.6f} {"N/A (disabled)":<20}')
    print(f'{"lambda_self 最大值":<30} {max(exp_lambda):<20.6f} {"0.0 (disabled)":<20}')
    print(f'{"lambda_self→行为因果证据":<30} {len(causal_evidence):<20} {"N/A":<20}')
    if causal_evidence:
        print(f'\n  因果证据详情（lambda上升 → 10 tick后 token 增加 > 20）:')
        for ev in causal_evidence[:5]:
            tick, lam0, lam1, tok0, tok1, dtok = ev
            print(f'    tick={tick}: lambda {lam0:.4f}→{lam1:.4f}, tokens {tok0}→{tok1} (+{dtok})')

    # 判定
    c1 = var_exp > var_ctrl
    c2 = sw_exp > sw_ctrl
    c3 = len(causal_evidence) > 0

    print("\n" + "=" * 70)
    print("判定结果")
    print("=" * 70)
    print(f"  [1] 实验组方差 > 对照组: {'PASS' if c1 else 'FAIL'} (exp={var_exp:.4f} vs ctrl={var_ctrl:.4f}, diff={var_exp-var_ctrl:+.4f})")
    print(f"  [2] 实验组切换次数 > 对照组: {'PASS' if c2 else 'FAIL'} (exp={sw_exp} vs ctrl={sw_ctrl}, diff={sw_exp-sw_ctrl})")
    print(f"  [3] lambda因果证据存在: {'PASS' if c3 else 'FAIL'} ({len(causal_evidence)} events)")

    all_pass = c1 and c2 and c3
    print(f"\n  总体判定: {'PASS（Lambda-Self 有效）' if all_pass else 'FAIL（Lambda-Self 未产生可观测效应）'}")

    # 保存判定报告
    report = {
        "experiment": "lambda_self_2group",
        "verdict": "PASS" if all_pass else "FAIL",
        "criteria": {
            "variance_exp_gt_ctrl": {"pass": c1, "exp_var": round(var_exp, 4), "ctrl_var": round(var_ctrl, 4)},
            "switches_exp_gt_ctrl": {"pass": c2, "exp_sw": sw_exp, "ctrl_sw": sw_ctrl},
            "lambda_causal_evidence": {"pass": c3, "count": len(causal_evidence)},
        },
        "summary_stats": {
            "exp_var": round(var_exp, 4), "ctrl_var": round(var_ctrl, 4),
            "exp_sw": sw_exp, "ctrl_sw": sw_ctrl,
            "exp_lambda_mean": round(sum(exp_lambda) / len(exp_lambda), 6),
            "causal_evidence_count": len(causal_evidence),
        }
    }
    report_path = os.path.join(OUT_DIR, "report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved: {report_path}")

    # 贴出每 10 tick 数据表（精简）
    print("\n" + "=" * 70)
    print("每 10 tick 数据表（实验组 vs 对照组）")
    print("=" * 70)
    print(f'{"tick":<6} {"EXP_lambda":<10} {"EXP_tok":<8} {"EXP_mode":<8} {"EXP_pt":<10} | {"CTRL_tok":<8} {"CTRL_mode":<8} {"CTRL_pt":<10}')
    print("-" * 90)

    def get_rows(rows):
        return [r for r in rows if r["tick"] % 10 == 0]

    exp_10 = get_rows(rows_exp)
    ctrl_10 = get_rows(rows_ctrl)
    max_show = min(len(exp_10), len(ctrl_10), 101)
    for idx in range(max_show):
        re = exp_10[idx]
        rc = ctrl_10[idx]
        print(f'{re["tick"]:<6} {re["lambda_self"]:<10.5f} {re["max_tokens"]:<8} {re["mode"]:<8} {re["pressure_term"]:<10.5f} | {rc["max_tokens"]:<8} {rc["mode"]:<8} {rc["pressure_term"]:<10.5f}')

    print("\nDONE.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
