#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在线学习核心验证实验

两组对比：
- A 组：学习器开启（LEARNING_LR = 0.01，W 更新）
- B 组：学习器关闭（覆盖 LEARNING_LR = 0.0，W 不更新但其他相同）

输入：完全相同的正向输入池（POSITIVE_INPUTS），1000 tick

每 50 tick 记录：
lambda_learn, err_ema, W_norm, max_tokens, mode, E, T, N, M, rp_ema, s_depth
"""

import csv
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

# ── LLM 桩（不调真实 LLM）──
import llm_interface
llm_interface.call_llm = lambda d, m: ""

from living_engine import (
    cold_start_if_needed,
    _save_json_atomic,
    LEARNING_LR,
    _update_luoshen_coupled,
    _compute_memory_emergence,
    _select_behavior,
    _encode_episodic_memory,
)
from run_r_experiment import POSITIVE_INPUTS, reset_memory

EXPERIMENT_DIR = os.path.join(SCRIPT_DIR, "learning_core_AB")
os.makedirs(EXPERIMENT_DIR, exist_ok=True)

TICKS = 1000
RECORD_INTERVAL = 50


def W_norm(W):
    return math.sqrt(sum(w * w for w in W))


def run_group(group_name, learn_lr):
    """运行单组"""
    # 覆盖学习率
    import living_engine
    original_lr = living_engine.LEARNING_LR
    living_engine.LEARNING_LR = learn_lr

    memory = cold_start_if_needed()
    # 初始化 ring_state（含 learning_core），与 run_r_experiment 一致
    memory["self_model"]["ring_state"] = {
        'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0,
        'relational_pressure_ema': 0.0,
        'ema_amp': 0.3, 'ema_ratio': 0.3,
        'ema_pv': 0.0, 'ema_pv2': 0.0,
        's_depth': 0.0,
        'lambda_self': 0.0,
        '_max_tokens_hist': [80.0, 80.0],
        '_rp_ema_hist': [0.0, 0.0],
        'learning_core': {},
        '_recent_tokens': [],
    }
    memory["internal_climate"] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    memory["user_model"]['total_interactions'] = 0
    memory["user_model"]['episodic_memory'] = [{
        'e_s': 0.5, 't_s': 0.0, 'n_s': 0.5,
        'salience': 0.6, 'kind': 'interaction',
        'timestamp': 1700000000.0, 'source_id': None,
    }]

    records = []

    # 合成环境（与 run_r_experiment.py 一致，确定性）
    SYNTHETIC_ENV = {
        'light': 0.7, 'noise': 0.02, 'temperature': 0.5,
        'humidity': 0.5, 'pressure': 0.5,
        '_phase': 0.0, '__prev_elapsed': 0, '__prev_cpu': 0,
    }

    for tick in range(1, TICKS + 1):
        # 构建合成环境（每 tick 更新 phase）
        env = dict(SYNTHETIC_ENV)
        env['_phase'] = (tick % 86400) / 86400.0
        env['_tick_id'] = tick

        # 直接调用 _update_luoshen_coupled（与 run_r_experiment.py 一致）
        _update_luoshen_coupled(memory, env, tick_id=tick)
        _encode_episodic_memory(memory)

        # 每 50 tick 记录
        if tick % RECORD_INTERVAL == 0:
            climate = memory.get("internal_climate", {})
            ring = memory.get("self_model", {}).get("ring_state", {})
            learning = memory.get("self_model", {}).get("learning_core", {})

            W = learning.get("W", [0.0] * 7)
            record = {
                "tick": tick,
                "group": group_name,
                "lambda_ema": 0.0,
                "err_ema": learning.get("err_ema", 0.0),
                "W_norm": round(W_norm(W), 6),
                "lambda_learn": learning.get("lambda_learn", 0.5),
                "E": round(climate.get("emotion_intensity", 0.5), 4),
                "T": round(climate.get("tension", 0.0), 4),
                "N": round(climate.get("energy", 0.5), 4),
                "M": round(climate.get("memory_pressure", 0.3), 4),
                "rp_ema": round(ring.get("relational_pressure_ema", 0.0), 4),
                "s_depth": round(ring.get("s_depth", 0.0), 4),
                "max_tokens": 0,
                "mode": "",
            }

            # 获取行为层输出（需要选一次行为获取 max_tokens）
            _compute_memory_emergence(memory)
            emergence = memory.get("__emergence", {})
            try:
                behavior = _select_behavior(memory, emergence)
                record["max_tokens"] = behavior.get("max_tokens", 0)
                record["mode"] = behavior.get("response_mode", "")
            except Exception:
                pass

            records.append(record)

    # 恢复原始 lr
    living_engine.LEARNING_LR = original_lr
    return records


def main():
    print("=" * 60)
    print("在线学习核心验证实验")
    print("=" * 60)

    print("\n运行 A 组（学习器开启，LR=0.01）...")
    records_A = run_group("A", learn_lr=0.01)
    print(f"  完成，记录 {len(records_A)} 条")

    print("\n运行 B 组（学习器关闭，LR=0.0）...")
    records_B = run_group("B", learn_lr=0.0)
    print(f"  完成，记录 {len(records_B)} 条")

    # 写 CSV
    csv_path = os.path.join(EXPERIMENT_DIR, "results.csv")
    fieldnames = ["tick", "group", "lambda_learn", "err_ema", "W_norm",
                  "max_tokens", "mode", "E", "T", "N", "M", "rp_ema", "s_depth"]
    all_records = records_A + records_B
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in all_records:
            writer.writerow(r)
    print(f"\nCSV 写入: {csv_path}")

    # 分析
    print("\n" + "=" * 60)
    print("分析")
    print("=" * 60)

    # W_norm 增长
    a_first = records_A[0]["W_norm"]
    a_last = records_A[-1]["W_norm"]
    b_first = records_B[0]["W_norm"]
    b_last = records_B[-1]["W_norm"]

    print(f"\nW_norm A 组: {a_first:.6f} -> {a_last:.6f}")
    print(f"W_norm B 组: {b_first:.6f} -> {b_last:.6f}")

    # 后期行为差异（tick >= 700）
    a_late = [r for r in records_A if r["tick"] >= 700]
    b_late = [r for r in records_B if r["tick"] >= 700]

    a_late_tokens = sum(r["max_tokens"] for r in a_late) / max(1, len(a_late))
    b_late_tokens = sum(r["max_tokens"] for r in b_late) / max(1, len(b_late))

    a_modes = set(r["mode"] for r in a_late)
    b_modes = set(r["mode"] for r in b_late)

    print(f"\nTick >= 700:")
    print(f"  A 组 avg max_tokens: {a_late_tokens:.2f}")
    print(f"  B 组 avg max_tokens: {b_late_tokens:.2f}")
    print(f"  A 组 modes: {a_modes}")
    print(f"  B 组 modes: {b_modes}")
    print(f"  差异: {abs(a_late_tokens - b_late_tokens):.2f}")

    # 判定
    criteria = []

    # 1. A 组 W_norm 应增长
    w_growth = a_last > a_first + 0.001
    criteria.append(("A 组 W_norm 增长", w_growth, f"{a_first:.6f} -> {a_last:.6f}"))

    # 2. 后期行为差异
    token_diff = abs(a_late_tokens - b_late_tokens)
    has_diff = token_diff > 5  # 至少差 5 tokens
    criteria.append(("Tick>=700 max_tokens 差异 > 5", has_diff, f"差异={token_diff:.2f}"))

    # 3. B 组 W 应不变
    b_unchanged = abs(b_last - b_first) < 0.0001
    criteria.append(("B 组 W_norm 不变", b_unchanged, f"{b_first:.6f} -> {b_last:.6f}"))

    print("\n" + "=" * 60)
    print("判定")
    print("=" * 60)
    for desc, passed, detail in criteria:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc} ({detail})")

    all_pass = all(p for _, p, _ in criteria)
    verdict = "PASS（学习器产生可测行为差异）" if all_pass else "FAIL（学习器未影响行为）"
    print(f"\n总体判定: {verdict}")

    # report
    report = {
        "experiment": "learning_core_AB",
        "ticks": TICKS,
        "criteria": {desc: passed for desc, passed, _ in criteria},
        "all_pass": all_pass,
        "verdict": verdict,
        "A_W_norm": {"first": a_first, "last": a_last},
        "B_W_norm": {"first": b_first, "last": b_last},
        "late_diff": token_diff,
    }
    import json
    with open(os.path.join(EXPERIMENT_DIR, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告写入: {os.path.join(EXPERIMENT_DIR, 'report.json')}")


if __name__ == "__main__":
    main()
