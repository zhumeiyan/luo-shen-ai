#!/usr/bin/env python3
"""
洛神长时间真实扰动实验

目标：在真实系统扰动下，观察洛神内部状态是否会出现设计外的倾向。

设计原则：
- 不加 LLM、不加用户输入干预
- 不加饥饿值 / 目标函数 / 反弹规则
- 不加随机数生成器作为扰动源（所有扰动来自真实系统采样）
- 不加"卡住就恢复"的逃逸机制
- 只观察，不拯救

运行 2000 tick，每个 tick：
  1. _sample_real_environment(env) — 从真实 Linux 系统采样
  2. _update_luoshen_coupled(memory, env, tick_id) — 洛神按自身方程演化
  3. 记录轨迹
"""

import json
import os
import sys
import time
import hashlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, ".")


# 载入living_engine（静默模式：不触发面向用户的回调）
import living_engine

TOTAL_TICKS = 2000
RESULTS_FILE = os.path.join(BASE, "experiment", "long_term_results.jsonl")
TRAJECTORY_FILE = os.path.join(BASE, "experiment", "long_term_trajectory.jsonl")


def main():
    print("=" * 70)
    print(f"长时间真实扰动实验 — {TOTAL_TICKS} ticks")
    print("=" * 70)

    # 加载初始记忆（与 A/B 实验同源）
    memory = living_engine._load_json("active_memory/active_memory.json")
    initial_state = memory.copy()

    # 确保从非零初始状态开始（避免原点锁定）
    memory["internal_climate"] = {
        "emotion_intensity": 0.5, "tension": 0.3,
        "energy": 0.5, "memory_pressure": 0.3
    }
    memory["__coupling_history"] = {
        "E": [0.5] * 4, "T": [0.3] * 4,
        "N": [0.5] * 4, "M": [0.3] * 4,
    }

    # 记录初始气候
    climate_init = memory.get("internal_climate", {})
    print(f"初始 E={climate_init.get('emotion_intensity')} "
          f"T={climate_init.get('tension')} "
          f"N={climate_init.get('energy')} "
          f"M={climate_init.get('memory_pressure')}")

    trajectory = []
    env_traj = []

    t_start = time.time()

    for tick_id in range(1, TOTAL_TICKS + 1):
        # ── 真实环境采样（来自 /proc、time、os.times 等）──
        env = living_engine._init_environment(memory)
        living_engine._sample_real_environment(env)

        # ── 洛神内部方程 + 真实扰动（不用 random 模块）──
        living_engine._update_luoshen_coupled(memory, env, tick_id=tick_id)

        # 记录轨迹
        climate = memory.get("internal_climate", {})
        trajectory.append({
            "tick": tick_id,
            "E": climate.get("emotion_intensity"),
            "T": climate.get("tension"),
            "N": climate.get("energy"),
            "M": climate.get("memory_pressure"),
            "env_noise": env.get("noise"),
            "env_light": env.get("light"),
            "env_temp": env.get("temperature"),
            "env_pressure": env.get("pressure"),
            "env_humidity": env.get("humidity"),
        })

        env_traj.append({
            "tick": tick_id,
            "noise": env.get("noise"),
            "light": env.get("light"),
            "temperature": env.get("temperature"),
            "pressure": env.get("pressure"),
            "humidity": env.get("humidity"),
        })

        # 进度（每 500 tick 打印一次）
        if tick_id % 500 == 0:
            elapsed = time.time() - t_start
            print(f"Tick {tick_id:5d}/{TOTAL_TICKS} | "
                  f"E={climate.get('emotion_intensity',0):.4f} "
                  f"T={climate.get('tension',0):.4f} "
                  f"N={climate.get('energy',0):.4f} "
                  f"M={climate.get('memory_pressure',0):.4f} | "
                  f"elapsed={elapsed:.1f}s")

    t_end = time.time()

    # 保存最终状态
    living_engine._save_json_atomic("active_memory/active_memory.json", memory)

    # 保存完整轨迹
    with open(TRAJECTORY_FILE, "w", encoding="utf-8") as f:
        for entry in trajectory:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 保存结果摘要
    result = {
        "experiment": "long_term_real_perturbation",
        "total_ticks": TOTAL_TICKS,
        "elapsed_seconds": round(t_end - t_start, 2),
        "initial_state": {
            "E": climate_init.get("emotion_intensity"),
            "T": climate_init.get("tension"),
            "N": climate_init.get("energy"),
            "M": climate_init.get("memory_pressure"),
        },
        "final_state": {
            "E": climate.get("emotion_intensity"),
            "T": climate.get("tension"),
            "N": climate.get("energy"),
            "M": climate.get("memory_pressure"),
        },
        "trajectory_file": TRAJECTORY_FILE,
        "total_interactions": memory.get("user_model", {}).get("total_interactions"),
    }
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print()
    print(f"完成。{TOTAL_TICKS} ticks，耗时 {t_end - t_start:.1f}s")
    print(f"最终 E={climate.get('emotion_intensity')} "
          f"T={climate.get('tension')} "
          f"N={climate.get('energy')} "
          f"M={climate.get('memory_pressure')}")
    print(f"轨迹写入：{TRAJECTORY_FILE}")
    print(f"结果写入：{RESULTS_FILE}")


if __name__ == "__main__":
    main()
