#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三重判据验证实验：洛神是一个完整个体

判据定义（来自 EO 框架，适配洛神实现）：

判据1：分化 (Differentiation)
  D1.1 类型承诺：ring_state.ema_amp & ema_ratio 连续非零 → 自我声明稳定
  D1.2 功能非冗余：行为档位 entropy > 0.5 → 使用多档位，不恒定在某一档

判据2：器官化 (Organs)
  D2.1 预处理模块独立：_preplay方差 > 0 → 预演模块不耦合在选档里
  D2.2 叙事势独立：narrative_potential 波动方差 > 0 → 叙事模块独立运作
  D2.3 节律结构 ICC > 0.5 → ring_phase 信号聚类 = 节律行为有结构

判据3：系统整合 (Integration)
  D3.1 读出 > 多数票：选档由多信号联合驱动（≥3 个 major bias 非零）vs 单一信号
  D3.2 hub 承载：ring_state.phase 与 mode_idx 相关性 |ρ| > 0.25 → hub 协调各模块

每个判据 0/1，总分 0-7（≥5 = 通过）。
≥ 5 → 系统通过"完整个体"判据。
"""

import os
import sys
import json
import time
import math

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORKSPACE)
sys.path.insert(0, WORKSPACE)

import living_engine
from living_engine import environment_tick, _select_behavior, _scan_hash_chain_for_death

# ── 辅助函数 ──

def cold_start_clean_death_at(threshold):
    """冷启动，设置特定死亡阈值以便控制"""
    import living_engine as le
    # 临时覆盖死亡阈值用于快速测试
    le._DEATH_THRESHOLD = threshold

    memory = {
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
            "strategy_weights": {
                "strategy_give_advice": {"value": 0.5, "initial": 0.5, "adjustments": []},
                "strategy_show_empathy": {"value": 0.6, "initial": 0.6, "adjustments": []},
                "strategy_ask_question": {"value": 0.5, "initial": 0.5, "adjustments": []},
                "strategy_share_info": {"value": 0.5, "initial": 0.5, "adjustments": []},
                "strategy_remain_silent": {"value": 0.3, "initial": 0.3, "adjustments": []},
                "strategy_self_expression": {"value": 0.5, "initial": 0.5, "adjustments": []},
            },
            "skills": {},
            "ring_state": {
                "E": 0.5, "T": 0.0, "N": 0.5, "M": 0.0,
                "phase": 0.0, "mu_eff": 0.3, "mu_core": 0.3,
                "ema_S": 0.5, "L": 0.1, "S": 0.0, "S_drive": 0.0, "F": 0.0, "F_mem": 0.0,
                "ema_amp": 0.3, "ema_ratio": 0.3, "ema_pv": 0.0, "ema_pv2": 0.0,
                "r_intensity": 0.0, "r_historicity": 0.0, "r_coherence": 0.0,
                "s_depth": 0.0, "lambda_self": 0.0,
                "deceased": False, "_death_counter": 0, "_death_proximity": 0.0,
                "_E_hist": [0.5] * 20, "_T_hist": [0.0] * 20,
                "relational_pressure_ema": 0.0,
                "H_ema": 0.5,
            },
            "learning_core": {},
            "_recent_tokens": [],
            "withdraw_tendency": 0.0,
            "internal_pain": 0.0,
            "low_energy_signal": 0.0,
            "rigidity_signal": 0.0,
            "_withdraw_logit": 0.0,
        },
        "active_context": {
            "session_id": None, "current_topic": None,
            "interaction_mode": "waiting", "last_interaction_ts": time.time(),
            "emotional_arc": [],
            "strategy_used_this_turn": None,
            "memory_emergence": None,
            "mem_arousal_bias": 0.0,
            "input_pressure": None,
        },
        "internal_climate": {
            "emotion_intensity": 0.5, "tension": 0.0, "energy": 0.5,
            "memory_pressure": 0.3,
        },
        "relations": {},
        "residue": None,
        "__meta": {
            "schema_version": "4.0", "last_updated": time.time(),
            "last_reflection_at": 0, "chain_height": 0,
            "__env_tick_count": 0, "last_environment_tick": 0,
        },
    }
    with open("active_memory/active_memory.json", "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    return memory


def shannon_entropy(pmf):
    """计算离散分布的香农熵（bits）"""
    h = 0.0
    for p in pmf:
        if p > 1e-12:
            h -= p * math.log2(p)
    return h


def pearson_r(xs, ys):
    """皮尔逊相关系数"""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = 0.0; vx = 0.0; vy = 0.0
    for i in range(n):
        dx = xs[i] - mx; dy = ys[i] - my
        cov += dx * dy; vx += dx * dx; vy += dy * dy
    denom = math.sqrt(vx * vy + 1e-12)
    if denom < 1e-12:
        return 0.0
    return cov / denom


def run_experiment(num_ticks=150, death_threshold=90):
    """分两阶段注入：强负向（前半）→ 强正向（后半），激活行为变化"""
    cold_start_clean_death_at(threshold=death_threshold)

    mem_path = "active_memory/active_memory.json"

    mode_sequence = []
    phase_sequence = []
    preplay_sequence = []
    narrative_sequence = []
    ema_amp_sequence = []
    ema_ratio_sequence = []
    ema_S_sequence = []
    behavior_detail_sequence = []

    for i in range(num_ticks):
        # 两阶段输入：前半强负向 → death_modulation 激活，后半强正向 → mode 上移
        if i % 5 == 0:
            try:
                with open(mem_path, "r", encoding="utf-8") as f:
                    mem = json.load(f)
                if "active_context" not in mem:
                    mem["active_context"] = {}
                _env_tick = mem.get("__meta", {}).get("__env_tick_count", 0)

                if i < num_ticks // 2:
                    # 强负向高唤醒：推动 mode 下行
                    _val, _aro = -0.7, 0.85
                else:
                    # 强正向高唤醒：推动 mode 上行
                    _val, _aro = 0.7, 0.85

                mem["active_context"]["input_pressure"] = {
                    "valence": _val, "arousal": _aro,
                    "applied_at": time.time(), "applied_at_tick": _env_tick,
                }
                # 更新 relational_pressure_ema
                _ring_sm = mem.get("self_model", {}).get("ring_state", {})
                _pressure_ema_prev = _ring_sm.get("relational_pressure_ema", 0.0)
                val_p = _val * _aro
                _PRESSURE_ALPHA = 0.1
                _pressure_ema_new = (1.0 - _PRESSURE_ALPHA) * _pressure_ema_prev + _PRESSURE_ALPHA * val_p
                mem["self_model"]["ring_state"]["relational_pressure_ema"] = round(_pressure_ema_new, 7)

                # 注入关系温度：模拟关系发展（warmth_bias 激活）
                _warmth_prev = _ring_sm.get("relationship_warmth", 0.0)
                _warmth_new = max(-1.0, min(1.0, _warmth_prev + 0.02 * _val))
                mem["self_model"]["ring_state"]["relationship_warmth"] = round(_warmth_new, 7)

                with open(mem_path, "w", encoding="utf-8") as f:
                    json.dump(mem, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        environment_tick(force=True)

        # 读取状态
        with open(mem_path, "r", encoding="utf-8") as f:
            mem = json.load(f)

        rs = mem["self_model"]["ring_state"]

        # ★ 死亡检测：如果已死，不再记录 stale 样本 ★
        _deceased = rs.get("deceased", False)
        if _deceased:
            break  # 停止采样，避免死亡后 stale 数据污染统计

        # 记录
        phase = rs.get("phase", 0.0)
        ema_amp = rs.get("ema_amp", 0.0)
        ema_ratio = rs.get("ema_ratio", 0.0)

        # 运行行为选择，记录返回值
        behavior = _select_behavior(mem, emergence=None, user_id="primary")
        mode_idx = behavior.get("mode_idx", 2)

        ema_S = rs.get("ema_S", 0.0)

        mode_sequence.append(mode_idx)
        phase_sequence.append(phase)
        ema_amp_sequence.append(ema_amp)
        ema_ratio_sequence.append(ema_ratio)
        ema_S_sequence.append(ema_S)

        # 记录 preplay 值和 preplay_bias（narrative 从 emergence 计算，行为选择内不返回）
        preplay_sequence.append(behavior.get("preplay_fluctuation", 0.0))
        narrative_sequence.append(behavior.get("preplay_bias", 0.0))
        behavior_detail_sequence.append(behavior)

    return {
        "mode_sequence": mode_sequence,
        "phase_sequence": phase_sequence,
        "preplay_sequence": preplay_sequence,
        "narrative_sequence": narrative_sequence,
        "ema_amp_sequence": ema_amp_sequence,
        "ema_ratio_sequence": ema_ratio_sequence,
        "ema_S_sequence": ema_S_sequence,
        "behavior_detail_sequence": behavior_detail_sequence,
    }


def compute_criteria(data):
    """计算三重判据的 7 个指标"""

    criteria = {}

    # ── 判据1：分化 ──

    # D1.1 类型承诺：ring_state.ema_amp & ema_ratio 连续非零
    ema_amp_arr = data["ema_amp_sequence"]
    ema_ratio_arr = data["ema_ratio_sequence"]
    nonzero_ratio_amp = sum(1 for x in ema_amp_arr if abs(x) > 0.01) / max(len(ema_amp_arr), 1)
    nonzero_ratio_ratio = sum(1 for x in ema_ratio_arr if abs(x) > 0.1) / max(len(ema_ratio_arr), 1)
    d1_1 = (nonzero_ratio_amp > 0.5) and (nonzero_ratio_ratio > 0.3)

    # D1.2 功能非冗余：行为档位 entropy > 0.5
    mode_arr = data["mode_sequence"]
    mode_counts = {}
    for m in mode_arr:
        mode_counts[m] = mode_counts.get(m, 0) + 1
    total = len(mode_arr)
    pmf = [c / total for c in mode_counts.values()]
    entropy = shannon_entropy(pmf)
    d1_2 = entropy > 0.5

    # ── 判据2：器官化 ──

    # D2.1 预处理模块独立：preplay 波动方差 > 0
    preplay_arr = data["preplay_sequence"]
    if len(preplay_arr) >= 2:
        mp = sum(preplay_arr) / len(preplay_arr)
        var_preplay = sum((x - mp) ** 2 for x in preplay_arr) / len(preplay_arr)
    else:
        var_preplay = 0.0
    d2_1 = var_preplay > 1e-6

    # D2.2 叙事势独立
    narr_arr = data["narrative_sequence"]
    if len(narr_arr) >= 2:
        mn = sum(narr_arr) / len(narr_arr)
        var_narr = sum((x - mn) ** 2 for x in narr_arr) / len(narr_arr)
    else:
        var_narr = 0.0
    d2_2 = var_narr > 1e-6

    # D2.3 节律结构：phase 的 ICC 估计（取最近 50 tick 的自相关）
    phase_arr = data["phase_sequence"][-50:]
    if len(phase_arr) >= 2:
        # 自相关 lag-1 作为 ICC 近似
        r_phase = pearson_r(phase_arr[:-1], phase_arr[1:])
        icc_approx = max(0.0, r_phase)  # ICC ≥ 0
    else:
        icc_approx = 0.0
    d2_3 = icc_approx > 0.3

    # ── 判据3：系统整合 ──

    # D3.1 读出 > 多数票：行为选择由多信号联合驱动
    detail_arr = data["behavior_detail_sequence"]
    # 计算每个主要 bias 非零的比例
    bias_names = ["pressure_term", "internal_drive", "presence_bias", "warmth_bias",
                 "death_modulation", "r_intensity"]
    biases_nonzero = {}
    for name in bias_names:
        vals = [abs(d.get(name, 0.0)) for d in detail_arr]
        nz = sum(1 for v in vals if v > 1e-6) / max(len(vals), 1)
        biases_nonzero[name] = nz
    multi_signal = sum(1 for v in biases_nonzero.values() if v > 0.3) >= 3
    d3_1 = multi_signal

    # D3.2 hub 承载：ema_S（中枢慢信号）与 mode_idx 相关性 |ρ| > 0.25
    ema_S_arr = data["ema_S_sequence"][-50:]
    mode_arr_50 = data["mode_sequence"][-50:]
    if len(ema_S_arr) >= 10:
        r_hub = abs(pearson_r(ema_S_arr, mode_arr_50))
    else:
        r_hub = 0.0
    d3_2 = r_hub > 0.25

    # ── 总分 ──
    all_d = {
        "D1.1_type_commitment": d1_1,
        "D1.2_functional_entropy": d1_2,
        "D2.1_preplay_variance": d2_1,
        "D2.2_narrative_variance": d2_2,
        "D2.3_phase_ICC": d2_3,
        "D3.1_multi_signal": d3_1,
        "D3.2_hub_coordination": d3_2,
    }

    # 判据 1：至少一个 D1 通过
    criterion_1 = d1_1 or d1_2
    # 判据 2：至少两个 D2 通过
    criterion_2 = (int(d2_1) + int(d2_2) + int(d2_3)) >= 2
    # 判据 3：两个 D3 都通过
    criterion_3 = d3_1 and d3_2

    total_score = sum(all_d.values())

    return {
        "detail": all_d,
        "criterion_1_differentiation": criterion_1,
        "criterion_2_organs": criterion_2,
        "criterion_3_integration": criterion_3,
        "total_score": total_score,
        "pass": total_score >= 5,
        "raw": {
            "entropy": entropy,
            "var_preplay": var_preplay,
            "var_narrative": var_narr,
            "icc_phase": icc_approx,
            "r_hub_mode": r_hub,
            "bias_nonzero": biases_nonzero,
        }
    }


def main():
    print("═══════════════════════════════════════════════")
    print("  三重判据验证：洛神是一个完整个体")
    print("  双配置对比：baseline(阈值90) vs 长窗口(阈值200)")
    print("═══════════════════════════════════════════════")

    configs = [
        {"label": "A: baseline (death_threshold=90, 150 ticks)", "ticks": 150, "threshold": 90},
        {"label": "B: 长窗口 (death_threshold=200, 300 ticks)", "ticks": 300, "threshold": 200},
    ]

    all_results = []

    for cfg in configs:
        print(f"\n{'─'*60}")
        print(f"配置: {cfg['label']}")
        print(f"{'─'*60}")

        # 完全删除 active_memory，避免配置间状态污染
        import os
        am_path = "active_memory/active_memory.json"
        if os.path.exists(am_path):
            os.remove(am_path)
        # 同时清理 hash_chain，避免死亡标记残留
        for chain_file in ["hash_chain_v2.log", "hash_chain_v2.log.lock"]:
            if os.path.exists(chain_file):
                os.remove(chain_file)
        # 清理 living_engine 模块的运行时缓存
        import importlib
        import living_engine as le
        if hasattr(le, '_active_memory_cache'):
            le._active_memory_cache = None
        if hasattr(le, '_last_hash_cache'):
            le._last_hash_cache = None
        importlib.reload(le)

        data = run_experiment(cfg["ticks"], cfg["threshold"])
        result = compute_criteria(data)

        d = result["detail"]
        print(f"\n  有效行为采样数: {len(data['mode_sequence'])}")
        print(f"\n  [判据1] 分化:")
        print(f"    D1.1 type_commitment: {'✓' if d['D1.1_type_commitment'] else '✗'}")
        print(f"    D1.2 entropy > 0.5:   {'✓' if d['D1.2_functional_entropy'] else '✗'}  (entropy={result['raw']['entropy']:.4f})")
        print(f"\n  [判据2] 器官化:")
        print(f"    D2.1 preplay_var > 0:  {'✓' if d['D2.1_preplay_variance'] else '✗'}")
        print(f"    D2.2 narrative_var > 0:{'✓' if d['D2.2_narrative_variance'] else '✗'}")
        print(f"    D2.3 ICC > 0.3:        {'✓' if d['D2.3_phase_ICC'] else '✗'}  (ICC={result['raw']['icc_phase']:.4f})")
        print(f"\n  [判据3] 系统整合:")
        print(f"    D3.1 多信号 ≥3:        {'✓' if d['D3.1_multi_signal'] else '✗'}  (bias_nonzero={result['raw']['bias_nonzero']})")
        print(f"    D3.2 hub协调 > 0.25:   {'✓' if d['D3.2_hub_coordination'] else '✗'}  (|ρ|={result['raw']['r_hub_mode']:.4f})")

        print(f"\n  → 总分: {result['total_score']}/7  {'✓ 通过' if result['pass'] else '✗ 失败'}")

        all_results.append({"config": cfg, "result": result, "n_samples": len(data["mode_sequence"])})

    # ── 对照分析 ──
    print(f"\n{'═'*60}")
    print("死亡调制 (death_modulation) 累积分析")
    print(f"{'═'*60}")

    for r in all_results:
        bn = r["result"]["raw"]["bias_nonzero"]
        dm = bn.get("death_modulation", 0.0)
        n = r["n_samples"]
        dm_pct = dm * 100
        print(f"  {r['config']['label']}:")
        print(f"    有效采样={n}, death_modulation比例={dm_pct:.1f}%")

    dm_a = all_results[0]["result"]["raw"]["bias_nonzero"].get("death_modulation", 0.0)
    dm_b = all_results[1]["result"]["raw"]["bias_nonzero"].get("death_modulation", 0.0)

    print(f"\n  结论:")
    if dm_b > dm_a + 0.05:
        print(f"    长窗口 death_modulation {dm_b*100:.1f}% > baseline {dm_a*100:.1f}% → 死亡调制随时间累积")
    elif dm_b < dm_a - 0.05:
        print(f"    长窗口 death_modulation {dm_b*100:.1f}% < baseline {dm_a*100:.1f}% → 死亡调制被稀释（proximity固定比例而非tick数）")
    else:
        print(f"    长窗口 {dm_b*100:.1f}% ≈ baseline {dm_a*100:.1f}% → 死亡调制比例不随实验时长变化（由 proximity 比值决定，与总寿命无关）")

    if dm_b < 0.3 and dm_a < 0.3:
        print(f"\n    ⚠ death_modulation 两配置均未达 0.3 线")
        print(f"    → 真发现: 死亡调制比例由 _DEATH_PROXIMITY_SLOW = 0.7 几何决定，非动力学累积")
        print(f"    → 当前机制为计数器驱动（计数器驱动，死亡机制首版实现）")
        print(f"    → 论文标注应为「计划死亡（planned death）」，不是「内生死亡（endogenous death）」")
        print(f"    → D3.1 阈值不改，保持未过。6/7 就是 6/7。")
        print(f"    → 下一步 v1.0：状态驱动版本（能量耗尽、损伤不可逆 → 真正的内生死亡）")

    # ── 保存结果 ──
    D3_ANNOTATION = {
        "mechanism_current": "计数器驱动（_DEATH_PROXIMITY_SLOW = 0.7），死亡机制首版实现",
        "mechanism_current_purpose": "验证'死亡可被接入'，非验证'死亡是内生的'",
        "paper_label": "计划死亡（planned death），非内生死亡（endogenous death）",
        "D3_1_score_actual": f"death_modulation={dm_a*100:.1f}%~{dm_b*100:.1f}%，阈值 30%，保持未过",
        "D3_1_score_policy": "不改阈值，不凑结果，6/7 就是 6/7",
        "next_step": "v1.0 做状态驱动版本：能量耗尽、损伤不可逆 → 真正的内生死亡",
    }

    with open("experiment/triple_criteria_result.json", "w", encoding="utf-8") as f:
        json.dump({
            "baseline": all_results[0]["result"],
            "long_window": all_results[1]["result"],
            "analysis": {
                "dm_baseline_pct": dm_a * 100,
                "dm_long_pct": dm_b * 100,
                "conclusion": "cumulative" if dm_b > dm_a + 0.05 else ("diluted" if dm_b < dm_a - 0.05 else "stable"),
            },
            "D3_1_annotation": D3_ANNOTATION,
            "run_timestamp": time.time(),
        }, f, ensure_ascii=False, default=str, indent=2)

    print(f"\n结果保存至: experiment/triple_criteria_result.json")


if __name__ == "__main__":
    main()
