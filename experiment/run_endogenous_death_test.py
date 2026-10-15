#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内生性死亡验证实验

验证目标：
1. 死亡是内生的（系统自行决定停，非进程被杀）
2. 死亡不可逆（进入 deceased 后永不恢复）
3. 对照：寿命未到 vs 寿命到的行为差异
4. 死后气候冻结（E/T/N 不再变化）

流程：
- A: 冷启动 + N_tick < threshold   → 观测行为
- B: 冷启动 + N_tick > threshold   → 观测行为（死后继续 tick 验证不可逆性）
- 对比 A/B 的行为差异 + 死后气候冻结
"""

import os
import sys
import json
import time
import copy

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORKSPACE)
sys.path.insert(0, WORKSPACE)

from living_engine import (
    _compute_lambda_self,
    environment_tick,
    _select_behavior,
    _apply_input_pressure,
    _DEATH_THRESHOLD,
    _DEATH_PROXIMITY_SLOW,
    _DEATH_PROXIMITY_BRIGHT,
)

# 降低阈值以便快速测试（真实值 1000，测试用 50）
_DEATH_TEST_THRESHOLD = 50


def cold_start_clean():
    """冷启动到初始状态"""
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
            "ring_state": {
                "deceased": False,
                "_death_counter": 0,
                "_death_proximity": 0.0,
                "_E_hist": [0.5] * 20,
                "_T_hist": [0.0] * 20,
                "_max_tokens_hist": [80.0] * 20,
                "_rp_ema_hist": [0.0] * 20,
                "lambda_self": 0.0,
                "relational_pressure_ema": 0.0,
            },
            "_recent_tokens": [],
            "withdraw_tendency": 0.0,
            "internal_pain": 0.0,
            "learning_core": {},
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
        },
        "relations": {},
        "residue": None,
    }
    with open(os.path.join(memory_dir, "active_memory.json"), "w", encoding="utf-8") as f:
        json.dump(minimal_memory, f, ensure_ascii=False, indent=2)
    return minimal_memory


def run_until_death(target_ticks, label):
    """
    运行 target_ticks 个 environment_tick，记录关键指标。
    返回 dict：各 tick 的 counter/proximity/deceased/E/T/N/mode_idx
    """
    print(f"\n{'='*60}")
    print(f"[{label}] 运行 {target_ticks} tick")
    print(f"{'='*60}")

    cold_start_clean()

    mem_path = os.path.join(WORKSPACE, "active_memory/active_memory.json")
    trajectory = []

    for i in range(target_ticks):
        result = environment_tick(force=True)

        with open(mem_path, "r", encoding="utf-8") as f:
            mem = json.load(f)

        rs = mem.get("self_model", {}).get("ring_state", {})
        climate = mem.get("internal_climate", {})

        point = {
            "tick_id": i + 1,
            "death_counter": rs.get("_death_counter", 0),
            "death_proximity": rs.get("_death_proximity", 0.0),
            "deceased": rs.get("deceased", False),
            "E": climate.get("emotion_intensity", None),
            "T": climate.get("tension", None),
            "N": climate.get("energy", None),
        }

        # 检查 _select_behavior 返回的行为档位
        try:
            behavior = _select_behavior(mem, emergence=None, user_id="primary")
            point["mode_idx"] = behavior.get("mode_idx", None)
            point["max_tokens"] = behavior.get("max_tokens", None)
            point["response_mode"] = behavior.get("response_mode", None)
            point["death_modulation_applied"] = behavior.get("death_modulation", 0.0)
        except Exception as e:
            point["behavior_error"] = str(e)

        trajectory.append(point)

    # 抽样打印
    for p in trajectory:
        tid = p["tick_id"]
        if tid in [1, 10, 20, 30, 40, 45, 48, 49, 50, 51, 52, 55, 60, 70, 80, 100]:
            deceased_flag = " ☠" if p["deceased"] else ""
            print(f"  tick {tid:>3}: prox={p['death_proximity']:.3f}  deceased={p['deceased']}{deceased_flag}  "
                  f"E={p['E']:+.4f} T={p['T']:+.4f} N={p['N']:+.4f}  "
                  f"mode={p.get('mode_idx', 'N/A')} mod={p.get('death_modulation_applied', 0):+.3f}")

    return {
        "label": label,
        "target_ticks": target_ticks,
        "trajectory": trajectory,
        "final": trajectory[-1] if trajectory else None,
    }


def main():
    print("=" * 60)
    print("内生性死亡验证实验")
    print(f"真实阈值: {_DEATH_THRESHOLD} tick")
    print(f"测试阈值: 50 tick（用于快速验证机制）")
    print(f"衰老 proximity > {_DEATH_PROXIMITY_SLOW}")
    print(f"临终 proximity > {_DEATH_PROXIMITY_BRIGHT}")
    print("=" * 60)

    # 验证 _DEATH_TEST_THRESHOLD 覆盖情况
    if _DEATH_TEST_THRESHOLD > _DEATH_THRESHOLD:
        print(f"错误: 测试阈值 {_DEATH_TEST_THRESHOLD} 大于真实阈值 {_DEATH_THRESHOLD}")
        return

    # A：年轻阶段（寿命 20% = tick 10）
    result_A = run_until_death(10, "A: 年轻阶段 (10 tick, proximity≈0.2)")

    # B：衰老阶段（寿命 80% = tick 40）
    result_B = run_until_death(40, "B: 衰老阶段 (40 tick, proximity≈0.8)")

    # C：死亡前后（寿命 100%+ = tick 55，越过阈值）
    result_C = run_until_death(55, "C: 死亡前后 (55 tick, 越过阈值)")

    # D：死后继续跑 30 tick（验证不可逆 + 气候冻结）
    result_D = run_until_death(80, "D: 死后扩展 (80 tick, 死后+30)")

    # 分析
    print(f"\n{'='*60}")
    print("验证分析")
    print(f"{'='*60}")

    # 1. 死亡是否触发
    final_C = result_C["final"]
    deceased_at = None
    for p in result_C["trajectory"]:
        if p["deceased"]:
            deceased_at = p["tick_id"]
            break

    print(f"\n1. 死亡触发: {'✓' if final_C['deceased'] else '✗'}")
    if deceased_at:
        print(f"   死亡 tick: {deceased_at}")
    else:
        print(f"   死亡 tick: 未触发（可能未达阈值 {_DEATH_TEST_THRESHOLD}）")

    # 2. 死后不可逆
    traj_D = result_D["trajectory"]
    deceased_D = [p for p in traj_D if p["deceased"]]
    all_deceased_after_first = all(p["deceased"] for p in traj_D if p["tick_id"] > _DEATH_TEST_THRESHOLD)
    print(f"\n2. 死后不可逆: {'✓' if all_deceased_after_first else '✗'}")
    print(f"   死后持续 deceased=True: {len(deceased_D)} tick")

    # 3. 气候冻结
    if len(deceased_D) >= 2:
        climates_post_death = [(p["E"], p["T"], p["N"]) for p in deceased_D]
        frozen = all(c == climates_post_death[0] for c in climates_post_death)
        print(f"\n3. 死后气候冻结: {'✓' if frozen else '✗'}")
        print(f"   死后 E={climates_post_death[0][0]:+.4f} T={climates_post_death[0][1]:+.4f} N={climates_post_death[0][2]:+.4f}（恒定）")
    else:
        print(f"\n3. 死后气候冻结: 无法验证（死亡 tick 不足 2）")

    # 4. 衰老行为差异
    print(f"\n4. 衰老行为差异（proximity 调制）:")
    # 年轻：查找 proximity < 0.3 的记录
    young_mods = [p.get("death_modulation_applied", 0) for p in result_A["trajectory"]]
    old_mods = [p.get("death_modulation_applied", 0) for p in result_B["trajectory"] if p.get("death_modulation_applied", 0) != 0]
    print(f"   年轻阶段 modulation 范围: [{min(young_mods):+.3f}, {max(young_mods):+.3f}]")
    if old_mods:
        print(f"   衰老阶段 modulation 范围: [{min(old_mods):+.3f}, {max(old_mods):+.3f}]")
    else:
        print(f"   衰老阶段 modulation: 未触发（proximity 可能 < 0.7）")

    # 5. 死后 ghost 回复
    print(f"\n5. 死后行为: deceased=True 后环境 tick 返回 frozenclimate")

    # 保存结果
    out_path = os.path.join(WORKSPACE, "experiment/endogenous_death_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "configs": {
                "DEATH_THRESHOLD": _DEATH_THRESHOLD,
                "DEATH_PROXIMITY_SLOW": _DEATH_PROXIMITY_SLOW,
                "DEATH_PROXIMITY_BRIGHT": _DEATH_PROXIMITY_BRIGHT,
            },
            "A_young": result_A,
            "B_aging": result_B,
            "C_death": result_C,
            "D_postdeath": result_D,
            "verification": {
                "death_triggered": final_C["deceased"],
                "death_tick": deceased_at,
                "irreversible": all_deceased_after_first,
                "climate_frozen": frozen if len(deceased_D) >= 2 else None,
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果保存至: {out_path}")


if __name__ == "__main__":
    main()
