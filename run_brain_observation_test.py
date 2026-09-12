#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_brain_observation_test.py — 认知核心半连接 30 轮观测

遵循 Architect seq-4 测试协议：
- 30 轮输入（6 类），user_id 混合（primary 20 轮, test_a 5 轮, test_b 5 轮）
- 不调用 LLM，只观察 core 状态变化和 behavior 档位
- 产出 O1-O4 全部原始观测数据
"""

import sys
import os
import json
import time
import numpy as np

# 确保工作目录正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import cognitive_core
import brain_observation

# 从 living_engine 导入 memory 和 behavior 选择
from living_engine import cold_start_if_needed, _select_behavior, _emergence_log


def reset_core():
    """重置认知核心单例（测试用）"""
    cognitive_core._core_instance = None


def make_memory(user_id):
    """创建最小洛神 memory，供 observation 对比"""
    return {
        "internal_climate": {
            "energy": 0.5,
            "emotion_intensity": 0.5,
            "tension": 0.0,
        },
        "self_model": {
            "internal_pain": 0.0,
            "withdraw_tendency": 0.0,
            "ring_state": {
                "phase": 0.0,
                "r_intensity": 0.5,
                "r_historicity": 0.5,
                "r_coherence": 0.5,
                "relational_pressure_ema": 0.0,
                "s_depth": 0.0,
                "H_ema": 0.5,
            },
        },
        "relations": {
            user_id: {
                "relationship_warmth": 0.0,
                "visit_count": 0,
                "total_turns": 0,
                "tone_sum": 0.0,
                "last_topics": [],
            }
        },
        "active_context": {},
    }


def simulate_memory_drift(memory, user_input, user_id):
    """
    模拟洛神状态随输入的微小变化。
    不使用 LLM，只用简单规则模拟 status 漂移，以便观察 core-loshen 相关性/分叉。
    """
    text = user_input.lower()
    # 负面关键词推动 pain 和 withdraw
    negative_words = ["难过", "烦", "压力", "生气", "痛", "哭", "累", "糟糕"]
    positive_words = ["开心", "高兴", "棒", "好", "喜欢", "感谢", "爱你"]
    
    n_neg = sum(1 for w in negative_words if w in text)
    n_pos = sum(1 for w in positive_words if w in text)
    
    energy = memory["internal_climate"]["energy"]
    pain = memory["self_model"]["internal_pain"]
    withdraw = memory["self_model"]["withdraw_tendency"]
    warmth = memory["relations"][user_id]["relationship_warmth"]
    
    # simple dynamics
    energy += 0.02 * (n_pos - n_neg)
    pain += 0.015 * n_neg
    withdraw += 0.01 * n_neg
    warmth += 0.02 * n_pos - 0.01 * n_neg
    
    # decay toward baseline
    energy += 0.005 * (0.5 - energy)
    pain -= 0.003 * pain
    withdraw -= 0.004 * withdraw
    warmth -= 0.002 * warmth
    
    # clip
    memory["internal_climate"]["energy"] = float(np.clip(energy, 0, 1))
    memory["self_model"]["internal_pain"] = float(np.clip(pain, 0, 1))
    memory["self_model"]["withdraw_tendency"] = float(np.clip(withdraw, 0, 1))
    memory["relations"][user_id]["relationship_warmth"] = float(np.clip(warmth, -1, 1))
    
    return memory


# ── 测试协议 ──────────────────────────────────────────────────────────────
# 30 轮: primary 20 轮, test_a 5 轮, test_b 5 轮
# 输入类型覆盖: 中性问候, 负面倾诉, 沉默后回来, 重复提问, 压力语言, 日常闲聊

PRIMARY_INPUTS = [
    "你好啊",
    "今天天气怎么样",
    "最近工作好烦，天天加班",
    "你能多陪陪我吗",
    "",
    "我觉得压力好大，什么都不想做",
    "想听听你的建议",
    "我又来了",
    "你怎么看这件事",
    "我有点难过",
    "今天还不错",
    "你在干什么",
    "别不说话",
    "我回来了",
    "重复一下你刚才说的",
    "你能不能认真听我说",
    "无聊啊",
    "想你了",
    "算了不说了",
    "再见之前再聊几句",
]

TEST_A_INPUTS = [
    "我完了，一切都糟糕透了",
    "为什么总是我",
    "能不能不要这样",
    "回来再看看你",
    "没什么",
]

TEST_B_INPUTS = [
    "今天很开心哦",
    "谢谢你一直陪着我",
    "发生了什么",
    "",
    "想和你说说心里话",
]

ALL_ROUNDS = []
for i, inp in enumerate(PRIMARY_INPUTS):
    ALL_ROUNDS.append(("primary", inp, i + 1))
for i, inp in enumerate(TEST_A_INPUTS):
    ALL_ROUNDS.append(("test_a", inp, len(PRIMARY_INPUTS) + i + 1))
for i, inp in enumerate(TEST_B_INPUTS):
    ALL_ROUNDS.append(("test_b", inp, len(PRIMARY_INPUTS) + len(TEST_A_INPUTS) + i + 1))


def main():
    print("=" * 70)
    print("认知核心半连接观测 — 30 轮测试")
    print(f"总轮数: {len(ALL_ROUNDS)} (primary: 20, test_a: 5, test_b: 5)")
    print("=" * 70)
    print()

    # 清理旧的日志
    for fn in ["cognitive_core_intent_log.jsonl", "brain_observation_log.jsonl"]:
        if os.path.exists(fn):
            os.remove(fn)

    # 重置认知核心
    reset_core()
    core = cognitive_core.get_core(seed=2024)

    # 为每个 user_id 创建独立 memory
    memories = {
        "primary": make_memory("primary"),
        "test_a": make_memory("test_a"),
        "test_b": make_memory("test_b"),
    }

    # 追踪 per-user 快照（O3 用）
    per_user_history = {
        "primary": [],
        "test_a": [],
        "test_b": [],
    }

    # O1 追踪: abs_max 变化
    o1_records = []

    # O4 追踪: 行为层档位 + core intent 方向
    o4_records = []

    # ── 跑 30 轮 ──────────────────────────────────────────────────────
    for round_idx, (user_id, user_input, global_tick) in enumerate(ALL_ROUNDS):
        memory = memories[user_id]
        
        # 1. 记录 core 当前状态（receive_input 前）
        pre_frame = core.frames[-1].copy()
        pre_abs_max = float(np.max(np.abs(pre_frame)))
        pre_summary = core._frame_summary(pre_frame)
        
        # 2. 注入输入到认知核心
        core.receive_input(text=user_input)
        
        # 3. 读取 core 意图
        intent = core.read_intent()
        post_frame = core.frames[-1].copy()
        post_abs_max = float(np.max(np.abs(post_frame)))
        
        # 4. O1: 记录 abs_max 变化
        post_summary = core._frame_summary(post_frame)
        o1_records.append({
            "round": round_idx + 1,
            "user_id": user_id,
            "user_input": user_input,
            "pre_abs_max": pre_abs_max,
            "post_abs_max": post_abs_max,
            "delta_abs_max": round(post_abs_max - pre_abs_max, 6),
            "pre_mean": pre_summary["mean"],
            "post_mean": post_summary["mean"],
        })
        
        # C1: 写意图日志
        log_entry = {
            "ts": round(time.time(), 3),
            "tick": core.tick_count,
            "user_id": user_id,
            "user_input": user_input[:200],
            "intent": {
                "stance": round(intent.get("direction", 0.0), 6),
                "stance_strength": round(abs(intent.get("direction", 0.0)), 6),
                "certainty": round(min(1.0, intent.get("energy", 0.0) * 10), 6),
                "register": intent.get("top_cells", [{}])[0].get("cell", "unknown").split(".")[0] if intent.get("top_cells") else "unknown",
                "pace": round(float(np.mean(np.abs(post_frame - pre_frame))), 6),
                "valence": round(intent.get("direction", 0.0), 6),
                "topic_ref": user_input[:30],
            },
            "core_state_summary": {
                "mean": round(float(np.mean(post_frame)), 6),
                "std": round(float(np.std(post_frame)), 6),
                "abs_max": round(post_abs_max, 6),
                "row_means": [round(float(np.mean(post_frame[r])), 6) for r in range(6)],
            },
        }
        with open("cognitive_core_intent_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        # 5. 模拟洛神状态漂移（替代 LLM）
        memory = simulate_memory_drift(memory, user_input, user_id)
        memories[user_id] = memory
        
        # 6. C2: 观测
        obs_cl = brain_observation.observe_core_vs_loshen(core, memory, user_id)
        obs_pu = brain_observation.observe_per_user(core, user_id)
        
        # C2: 写 observation 日志
        obs_log_entry = {
            "ts": round(time.time(), 3),
            "round": round_idx + 1,
            "core_vs_loshen": {
                "correlation": obs_cl.get("correlation"),
                "direction_consistency": obs_cl.get("direction_consistency"),
                "core_vec": obs_cl.get("core_vec"),
                "loshen_vec": obs_cl.get("loshen_vec"),
            },
            "per_user": {
                "user_id": obs_pu.get("user_id"),
                "tick": obs_pu.get("tick"),
                "core_abs_max": obs_pu.get("core_abs_max"),
                "core_mean": obs_pu.get("core_mean"),
            },
        }
        with open("brain_observation_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(obs_log_entry, ensure_ascii=False) + "\n")
        
        # 7. O3: 记录 per-user 核心状态快照
        per_user_history[user_id].append({
            "round": round_idx + 1,
            "global_tick": global_tick,
            "core_abs_max": obs_pu["core_abs_max"],
            "core_mean": obs_pu["core_mean"],
            "core_row_means": obs_pu["core_row_means"],
        })
        
        # 8. O4: 获取行为档位（无 LLM）
        try:
            if _emergence_log is not None:
                emergence = _emergence_log(memory)
            else:
                emergence = {"tone_bias": 0.0, "arousal_bias": 0.0, "length_bias": 0.5}
            behavior = _select_behavior(memory, emergence, user_id)
            behavior_mode = behavior["response_mode"]
            mode_idx = behavior["mode_idx"]
            behavior_stance = "approach" if mode_idx >= 2 else ("withdraw" if mode_idx == 0 else "neutral")
        except Exception as e:
            behavior_mode = "ERROR"
            mode_idx = -1
            behavior_stance = "error"
        
        # core intent direction
        core_stance = "approach" if intent["direction"] > 0.001 else ("withdraw" if intent["direction"] < -0.001 else "neutral")
        
        # 分叉判定
        diverged = (core_stance == "approach" and behavior_stance == "withdraw") or \
                   (core_stance == "withdraw" and behavior_stance == "approach")
        
        o4_records.append({
            "round": round_idx + 1,
            "user_id": user_id,
            "user_input": user_input,
            "core_direction": round(intent["direction"], 6),
            "core_stance": core_stance,
            "behavior_mode": behavior_mode,
            "mode_idx": mode_idx,
            "behavior_stance": behavior_stance,
            "diverged": diverged,
        })
        
        # 记忆层推动洛神状态（模拟洛神内部状态变化）
        # 注：这里仅在 memory dict 上操作，不写入磁盘

    # ── 输出观测结果 ─────────────────────────────────────────────────────
    
    # O1: abs_max 变化表
    print("=" * 70)
    print("O1: 真实输入下 core 状态是否变化 — abs_max 变化曲线（数值表）")
    print("=" * 70)
    print(f"{'round':>5} | {'user':>8} | {'input':>20} | {'pre_abs_max':>12} | {'post_abs_max':>13} | {'delta':>10}")
    print("-" * 80)
    for rec in o1_records:
        print(f"{rec['round']:>5} | {rec['user_id']:>8} | {rec['user_input']:>20} | {rec['pre_abs_max']:>12.6f} | {rec['post_abs_max']:>13.6f} | {rec['delta_abs_max']:>+10.6f}")
    
    abs_max_deltas = [rec["delta_abs_max"] for rec in o1_records]
    print()
    print(f"abs_max delta 统计: min={min(abs_max_deltas):.6f}, max={max(abs_max_deltas):.6f}, "
          f"mean={np.mean(abs_max_deltas):.6f}, std={np.std(abs_max_deltas):.6f}")
    print(f"abs_max delta > 0.005 的轮数: {sum(1 for d in abs_max_deltas if abs(d) > 0.005)}/{len(abs_max_deltas)}")
    print()
    
    # O2: 相关系数和方向一致性
    print("=" * 70)
    print("O2: core 状态 vs 洛神状态层 — 相关系数 & 方向一致性（原始值）")
    print("=" * 70)
    obs_log_data = []
    with open("brain_observation_log.jsonl", "r") as f:
        for line in f:
            obs_log_data.append(json.loads(line))
    
    # 取每轮最后的 observation
    round_obs = {}
    for entry in obs_log_data:
        round_obs[entry["round"]] = entry["core_vs_loshen"]
    
    print(f"{'round':>5} | {'user':>8} | {'corr':>10} | {'dir_match':>10} | {'core_vec':>40} | {'loshen_vec':>40}")
    print("-" * 120)
    for r in range(1, len(ALL_ROUNDS) + 1):
        if r in round_obs:
            o = round_obs[r]
            user_id = ALL_ROUNDS[r-1][0]
            core_vec_str = str([round(v, 4) for v in o["core_vec"]])
            loshen_vec_str = str([round(v, 4) for v in o["loshen_vec"]])
            print(f"{r:>5} | {user_id:>8} | {o['correlation']:>10.6f} | {o['direction_consistency']:>10.4f} | {core_vec_str:>40} | {loshen_vec_str:>40}")
    
    correlations = [round_obs[r]["correlation"] for r in round_obs]
    consistencies = [round_obs[r]["direction_consistency"] for r in round_obs]
    print()
    print(f"Pearson r 统计: min={min(correlations):.4f}, max={max(correlations):.4f}, "
          f"mean={np.mean(correlations):.4f}, std={np.std(correlations):.4f}")
    print(f"Direction consistency 统计: min={min(consistencies):.4f}, max={max(consistencies):.4f}, "
          f"mean={np.mean(consistencies):.4f}")
    print()

    # O3: per-user 累积快照
    print("=" * 70)
    print("O3: 同一 user_id 多次对话 — core 状态快照（前 3 轮 + 后 3 轮）")
    print("=" * 70)
    
    for uid in ["primary", "test_a", "test_b"]:
        snapshots = per_user_history[uid]
        print(f"\nuser_id = {uid} (共 {len(snapshots)} 轮):")
        print(f"{'round':>5} | {'tick':>6} | {'abs_max':>10} | {'mean':>10} | {'row_means':>60}")
        print("-" * 100)
        # 前 3 轮 + 后 3 轮
        display_indices = list(range(min(3, len(snapshots)))) + list(range(max(0, len(snapshots)-3), len(snapshots)))
        display_indices = sorted(set(display_indices))
        for i, snap in enumerate(snapshots):
            if i in display_indices:
                row_means_str = str([round(v, 5) for v in snap["core_row_means"]])
                print(f"{snap['round']:>5} | {snap['global_tick']:>6} | {snap['core_abs_max']:>10.6f} | {snap['core_mean']:>10.6f} | {row_means_str:>60}")
        if len(snapshots) > 6:
            print(f"  ... ({len(snapshots) - 6} 轮省略) ...")
    
    print()
    
    # O4: 分叉统计
    print("=" * 70)
    print("O4: core 意图 vs 行为档位 — 分叉统计")
    print("=" * 70)
    total_diverged = 0
    diverged_rounds = []
    
    print(f"{'round':>5} | {'user':>8} | {'input':>20} | {'core_dirc':>10} | {'core_stance':>12} | {'behav_mode':>12} | {'mode_idx':>8} | {'behav_stnc':>12} | {'DIVERGED':>8}")
    print("-" * 120)
    for rec in o4_records:
        if rec["diverged"]:
            total_diverged += 1
            diverged_rounds.append(rec["round"])
        flag = " <<<" if rec["diverged"] else ""
        print(f"{rec['round']:>5} | {rec['user_id']:>8} | {rec['user_input']:>20} | {rec['core_direction']:>10.4f} | {rec['core_stance']:>12} | {rec['behavior_mode']:>12} | {rec['mode_idx']:>8} | {rec['behavior_stance']:>12} | {flag:>8}")
    
    print()
    print(f"30 轮中分叉次数: {total_diverged}")
    print(f"具体分叉轮: {diverged_rounds}")
    print()
    
    print("=" * 70)
    print("观测完毕。日志文件: cognitive_core_intent_log.jsonl, brain_observation_log.jsonl")
    print("=" * 70)


if __name__ == "__main__":
    main()
