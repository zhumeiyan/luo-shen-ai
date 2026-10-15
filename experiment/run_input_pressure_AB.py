#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
输入压力通道 A/B 验证实验（无 LLM 版）

绕过 generate_response 的 LLM 调用，直接：
1. cold_start_clean
2. 调用 _apply_input_pressure 直接写入模拟的 pressure（不依赖 LLM）
3. 读取 internal_climate → climate_after
4. 执行 N 次 environment_tick
5. 记录气候轨迹

验证目标：不同 (valence, arousal) 产生可观测的 climate 差异。
"""

import os
import sys
import json
import time
import copy

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORKSPACE)
sys.path.insert(0, WORKSPACE)

# 直接从 living_engine 导入需要的函数
from living_engine import (
    _apply_input_pressure,
    _update_luoshen_coupled,
    environment_tick,
    _init_residue,
    _compute_memory_emergence,
    _encode_episodic_memory,
    _evolve_climate_idle,
)


def cold_start_clean():
    """清空活记忆层到冷启动默认状态"""
    memory_dir = os.path.join(WORKSPACE, "active_memory")
    os.makedirs(memory_dir, exist_ok=True)
    minimal_memory = {
        "user_model": {
            "known_facts": {"facts": [], "last_update": 0},
            "episodic_memory": [],
            "total_interactions": 0,
            "shared_history_length": 0,
            "intimacy": {"value": 0.5},
            "emotional_patterns": [],
        },
        "self_model": {
            "emotion": {"primary": "平静", "intensity": 0.5},
            "self_stated_state": {"last_stated": None, "last_stated_at": 0},
            "strategy_weights": {},
            "ring_state": {},
            "_recent_tokens": [],
        },
        "active_context": {
            "interaction_mode": "normal",
            "last_interaction_ts": 0,
            "emotional_arc": [],
            "strategy_used_this_turn": None,
            "memory_emergence": None,
            "mem_arousal_bias": 0.0,
            "input_pressure": None,
        },
        "internal_climate": {
            "emotion_intensity": 0.5,
            "tension": 0.0,
            "energy": 0.5,
            "memory_pressure": 0.3,
        },
        "__meta": {
            "last_updated": time.time(),
            "__env_tick_count": 0,
            "last_environment_tick": 0,
            "schema_version": "4.0",
            "last_reflection_at": 0,
            "chain_height": 0,
        },
        "relations": {},
        "residue": None,
    }
    with open(os.path.join(memory_dir, "active_memory.json"), "w", encoding="utf-8") as f:
        json.dump(minimal_memory, f, ensure_ascii=False, indent=2)
    return minimal_memory


def simulate_pressure_injection(memory, valence, arousal):
    """
    模拟 _apply_input_pressure 的存储行为，不依赖 LLM。
    直接写入 active_context["input_pressure"]。
    """
    if "active_context" not in memory:
        memory["active_context"] = {}

    _env_tick = memory.get("__meta", {}).get("__env_tick_count", 0)
    memory["active_context"]["input_pressure"] = {
        "valence": round(valence, 4),
        "arousal": round(arousal, 4),
        "applied_at": time.time(),
        "applied_at_tick": _env_tick,
    }

    # 同时更新 relational_pressure_ema（与真实 _apply_input_pressure 一致）
    val_p = valence * arousal
    _ring_sm = memory.get("self_model", {}).get("ring_state", {})
    _pressure_ema_prev = _ring_sm.get("relational_pressure_ema", 0.0)
    _PRESSURE_ALPHA = 0.02
    _pressure_ema_new = (1.0 - _PRESSURE_ALPHA) * _pressure_ema_prev + _PRESSURE_ALPHA * val_p
    if "self_model" not in memory:
        memory["self_model"] = {}
    if "ring_state" not in memory["self_model"]:
        memory["self_model"]["ring_state"] = {}
    memory["self_model"]["ring_state"]["relational_pressure_ema"] = round(_pressure_ema_new, 7)

    return memory


def run_single_pressure_test(valence, arousal, label):
    """
    执行一轮压力测试：
    1. cold_start
    2. 直接写入压力（模拟 LLM 提取）
    3. 记录交互后气候
    4. 执行 N 个 environment_tick
    5. 记录气候轨迹
    """
    print(f"\n{'='*60}")
    print(f"[{label}] valence={valence:+.3f}  arousal={arousal:+.3f}")
    print(f"{'='*60}")

    memory = cold_start_clean()

    # 直接写入压力（绕过 LLM）
    memory = simulate_pressure_injection(memory, valence, arousal)

    # 立即写入磁盘（模拟 update_after_interaction 的持久化）
    mem_path = os.path.join(WORKSPACE, "active_memory/active_memory.json")
    with open(mem_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

    # 读取气候（交互后）
    climate_after = memory.get("internal_climate", {})
    pressure_stored = memory.get("active_context", {}).get("input_pressure")
    print(f"\n交互后气候 (尚未直接修改 — 压力在 active_context 中):")
    print(f"  E={climate_after.get('emotion_intensity', 'N/A'):.4f}")
    print(f"  T={climate_after.get('tension', 'N/A'):.4f}")
    print(f"  N={climate_after.get('energy', 'N/A'):.4f}")
    print(f"  存储的压力: v={pressure_stored['valence']:.3f}  a={pressure_stored['arousal']:.3f}  tick={pressure_stored['applied_at_tick']}")

    # 执行 N 个 tick
    NUM_TICKS = 30
    print(f"\n执行 {NUM_TICKS} 个 environment_tick:")
    trajectory = []
    for i in range(NUM_TICKS):
        tick_result = environment_tick(force=True)
        # 读取当前气候
        with open(mem_path, "r", encoding="utf-8") as f:
            mem = json.load(f)
        climate = mem.get("internal_climate", {})
        tick_id = tick_result.get("tick_id", i + 1)
        point = {
            "tick_id": tick_id,
            "E": climate.get("emotion_intensity", 0),
            "T": climate.get("tension", 0),
            "N": climate.get("energy", 0),
            "M": climate.get("memory_pressure", 0),
        }
        trajectory.append(point)

    # 打印每 5 tick 一次
    for p in trajectory:
        if p["tick_id"] % 5 == 0 or p["tick_id"] == 1:
            print(f"  tick {p['tick_id']:>3}: E={p['E']:+.4f}  T={p['T']:+.4f}  N={p['N']:+.4f}  M={p['M']:+.4f}")

    # 最终气候
    if trajectory:
        final = trajectory[-1]
        print(f"\n最终 tick {final['tick_id']}: E={final['E']:+.4f}  T={final['T']:+.4f}  N={final['N']:+.4f}")

    return {
        "label": label,
        "valence": valence,
        "arousal": arousal,
        "climate_after_interaction": climate_after,
        "pressure_stored": pressure_stored,
        "trajectory": trajectory,
    }


def main():
    print("=" * 60)
    print("输入压力通道 A/B 验证实验（无 LLM）")
    print("=" * 60)

    # A: 负向高唤醒（v=-0.6, a=0.7）
    result_A = run_single_pressure_test(
        valence=-0.6,
        arousal=0.7,
        label="A: 负向高唤醒（害怕离开）"
    )

    # B: 中性低唤醒（v=0.05, a=0.15）
    result_B = run_single_pressure_test(
        valence=0.05,
        arousal=0.15,
        label="B: 中性低唤醒（天气好）"
    )

    # C: 正向高唤醒（v=0.7, a=0.8）— 额外对照组
    result_C = run_single_pressure_test(
        valence=0.7,
        arousal=0.8,
        label="C: 正向高唤醒（兴奋好消息）"
    )

    # 对比
    print(f"\n{'='*60}")
    print("气候差异对比")
    print(f"{'='*60}")

    # 注意：交互后气候无差异（压力还没进入微分方程）
    ca = result_A["climate_after_interaction"]
    cb = result_B["climate_after_interaction"]
    print(f"\n交互后气候（A=B — 证明压力不直接赋值）:")
    print(f"  A: E={ca.get('emotion_intensity', 0):.4f} T={ca.get('tension', 0):.4f} N={ca.get('energy', 0):.4f}")
    print(f"  B: E={cb.get('emotion_intensity', 0):.4f} T={cb.get('tension', 0):.4f} N={cb.get('energy', 0):.4f}")

    # 对比轨迹
    print(f"\n轨迹对比（微分方程注入压力，应衰减收敛）:")
    print(f"{'Tick':>5} | {'A_E':>8} {'A_T':>8} {'A_N':>8} | {'B_E':>8} {'B_T':>8} {'B_N':>8} | {'ΔE':>8} {'ΔT':>8} {'ΔN':>8}")
    print("-" * 95)

    min_len = min(len(result_A["trajectory"]), len(result_B["trajectory"]))
    de_max = dt_max = dn_max = 0
    for i in range(min_len):
        a = result_A["trajectory"][i]
        b = result_B["trajectory"][i]
        de = abs(a["E"] - b["E"])
        dt = abs(a["T"] - b["T"])
        dn = abs(a["N"] - b["N"])
        de_max = max(de_max, de)
        dt_max = max(dt_max, dt)
        dn_max = max(dn_max, dn)
        if a["tick_id"] % 5 == 0 or a["tick_id"] == 1:
            print(f"  {a['tick_id']:>3} | {a['E']:>+8.4f} {a['T']:>+8.4f} {a['N']:>+8.4f} | {b['E']:>+8.4f} {b['T']:>+8.4f} {b['N']:>+8.4f} | {de:>8.4f} {dt:>8.4f} {dn:>8.4f}")

    # 最终差异
    a_final = result_A["trajectory"][min_len - 1]
    b_final = result_B["trajectory"][min_len - 1]
    de_final = abs(a_final["E"] - b_final["E"])
    dt_final = abs(a_final["T"] - b_final["T"])
    dn_final = abs(a_final["N"] - b_final["N"])

    print(f"\n最大差异 (tick 1-N):")
    print(f"  max ΔE = {de_max:.4f}")
    print(f"  max ΔT = {dt_max:.4f}")
    print(f"  max ΔN = {dn_max:.4f}")
    print(f"\n最终 tick 差异:")
    print(f"  ΔE = {de_final:.4f}")
    print(f"  ΔT = {dt_final:.4f}")
    print(f"  ΔN = {dn_final:.4f}")

    # 判定
    threshold = 0.05
    passed_max = de_max > threshold or dt_max > threshold or dn_max > threshold
    passed_final = de_final > threshold or dt_final > threshold or dn_final > threshold

    print(f"\n判定（阈值 {threshold}）:")
    print(f"  最大差异: {'✓ 通过' if passed_max else '✗ 失败'}")
    print(f"  最终差异: {'✓ 通过' if passed_final else '✗ 失败'}")
    if passed_max:
        print(f"  ✓ 压力通道有效 — 不同输入在微分方程中产生了可观测的动力学差异")
    else:
        print(f"  ✗ 压力通道无效 — 差异未达到可观测量级")

    # A vs C 对比（同是高唤醒但方向相反）
    print(f"\n{'='*60}")
    print(f"A (负向) vs C (正向) 对比 — 方向一致性检验")
    print(f"{'='*60}")
    # A 是负向高唤醒（v=-0.6, a=0.7）→ 预期降低 E（dE 为负）
    # C 是正向高唤醒（v=0.7, a=0.8）→ 预期提升 E（dE 为正）
    # 如果通道有效，A 的 E 应该低于 C

    a_E_5 = result_A["trajectory"][min(4, min_len-1)]["E"]  # tick ~5
    c_E_5 = result_C["trajectory"][min(4, min_len-1)]["E"]
    direction_ok = a_E_5 < c_E_5
    print(f"  tick 5: A_E={a_E_5:+.4f}  C_E={c_E_5:+.4f}  →  A < C: {'✓' if direction_ok else '✗'}")
    print(f"  判定: {'✓ 方向一致' if direction_ok else '✗ 方向反转（可能有问题）'}")

    # 保存结果
    out_path = os.path.join(WORKSPACE, "experiment/input_pressure_AB_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "A": {k: v for k, v in result_A.items() if k != "trajectory"},
            "B": {k: v for k, v in result_B.items() if k != "trajectory"},
            "C": {k: v for k, v in result_C.items() if k != "trajectory"},
            "trajectories": {
                "A": result_A["trajectory"],
                "B": result_B["trajectory"],
                "C": result_C["trajectory"],
            },
            "summary": {
                "max_diff_E": de_max,
                "max_diff_T": dt_max,
                "max_diff_N": dn_max,
                "final_diff_E": de_final,
                "final_diff_T": dt_final,
                "final_diff_N": dn_final,
                "threshold": threshold,
                "passed_max": passed_max,
                "passed_final": passed_final,
                "direction_test": direction_ok,
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果保存至: {out_path}")


if __name__ == "__main__":
    main()
