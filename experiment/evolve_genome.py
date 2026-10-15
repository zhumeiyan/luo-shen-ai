#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
达尔文式进化实验：洛神参数基因组的自然选择

设计思路（"野败"法）：
1. 种群 = 16 个个体，每个个体的基因组是洛神模块参数的微扰版本
2. 个体在标准测试环境中跑固定拍数（平静→压力→恢复→正向四阶段）
3. 适应度评分：长寿 + 稳定性 + 响应性 三维度
4. 选择：保留前 50%，交叉繁殖 + 高斯变异
5. 迭代 10 代，记录适应度轨迹和被筛选出的参数组合

不是梯度下降，不是训练。是变异+选择+遗传。
与 EO 条件对齐：死亡（寿命限制）+ 稀缺（资源有限）+ 代谢（能量系统）

标签：实现验证，非证据。
"""

import os
import sys
import json
import time
import math
import random
import copy

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORKSPACE)
sys.path.insert(0, WORKSPACE)

import living_engine as le

# ────────────────────────────────────────────
# 基因组定义（15 个可进化参数）
# ────────────────────────────────────────────
GENOME_KEYS = [
    # 行为层
    "_K_WARMTH",           # relationship warmth bias 强度
    "_PRESSURE_K",         # 压力系数
    "_WITHDRAW_ACCUM_RATE", # 退缩积累率
    "_NARRATIVE_TENDENCY_BOOST", # 叙事增强倍率
    # 死亡层
    "_DEATH_PROXIMITY_SLOW",     # 衰老起始阈值
    "_DEATH_PROXIMITY_BRIGHT",   # 临终阈值
    "_AGING_SLOW_THRESHOLD",     # aging_signal 慢阈值
    "_AGING_BRIGHT_THRESHOLD",   # aging_signal 亮阈值
    # 能量层
    "_ENERGY_INPUT_RATE",        # 能量输入率
    "_ENERGY_DRAIN_BASE",        # 能量基础消耗
    "_DAMAGE_RATE",              # 基础损伤率
    "_REPAIR_RATE",              # 修复率
    # 节律层
    "_R_ALPHA_ENERGY",           # r_intensity EMA 平滑
    "_R_ALPHA_HIST",             # r_historicity EMA 平滑
    "_LAMBDA_SELF_ALPHA",        #僵化检测增益
]

def get_base_genome():
    """从当前洛神模块获取基线基因组"""
    g = {}
    for k in GENOME_KEYS:
        g[k] = getattr(le, k, 0.0)
    return g

def apply_genome(genome):
    """将基因组应用到模块级常量"""
    for k, v in genome.items():
        setattr(le, k, v)

def mutate_genome(genome, scale=0.2):
    """高斯变异：每个参数 × (1 + N(0, scale))，保持正值"""
    mutant = {}
    for k, v in genome.items():
        noise = random.gauss(0, scale)
        new_val = v * (1.0 + noise)
        # 硬下限：所有参数必须 > 0
        if new_val < 1e-6:
            new_val = 1e-6
        # 界限：不超过原始的 5 倍
        max_val = abs(v) * 5.0 if v != 0 else 1.0
        if new_val > max_val:
            new_val = max_val
        mutant[k] = new_val
    return mutant

def crossover_genome(g1, g2):
    """均匀交叉：每个参数随机来自父或母"""
    child = {}
    for k in GENOME_KEYS:
        if random.random() < 0.5:
            child[k] = g1[k]
        else:
            child[k] = g2[k]
    return child

# ────────────────────────────────────────────
# 环境清理
# ────────────────────────────────────────────
def clean_all():
    """完全清理 population 实验的前置状态"""
    import glob
    for f in ["active_memory/active_memory.json", "hash_chain_v2.log",
              "hash_chain_v2.log.lock", "active_memory/environment_log.jsonl"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

def reload_engine():
    """重载引擎模块以重置所有状态"""
    import importlib
    importlib.reload(le)

# ────────────────────────────────────────────
# 适应度评估
# ────────────────────────────────────────────
# 测试阶段定义
# (阶段名, 拍数, 压力valence, 压力arousal)
TEST_PHASES = [
    ("calm",    150,  0.0,  0.2),   # 平静期：基线观察
    ("stress",  300, -0.7,  0.9),   # 压力期：强负向高唤醒
    ("recovery",150,  0.0,  0.3),   # 恢复期：零输入
    ("positive",100, +0.6,  0.5),   # 正向期：温和正输入
]
TOTAL_TEST_TICKS = sum(p[1] for p in TEST_PHASES)  # = 700

# 适应性权重
W_SURVIVAL = 0.5    # 长寿权重
W_STABILITY = 0.3   # 稳定性权重
W_RESPONSE  = 0.2   # 响应性权重

def run_individual(genome, uid):
    """
    运行一个个体，返回 (survival, stability, response, fitness) 四元组
    """
    clean_all()
    reload_engine()
    apply_genome(genome)

    # 设置死亡相关常量
    le._DEATH_V1 = True
    le._DEATH_ACT = False  # 只用状态驱动

    # 跟踪指标
    survival_ticks = 0
    alive = True
    phase_metrics = {}  # {"calm": {"E": [...], "T": [...], ...}, ...}
    stress_response_delta = None  # 压力期的平均变化

    tick = 0
    current_phase_idx = 0
    phase_tick = 0

    E_trace = []  # 全程 E 跟踪（用于稳定性计算）

    while tick < TOTAL_TEST_TICKS and alive:
        # 确定当前阶段注入的压力
        phase_name, phase_len, val_inj, aro_inj = TEST_PHASES[current_phase_idx]

        # 注入压力
        mem_path = "active_memory/active_memory.json"
        if os.path.exists(mem_path):
            with open(mem_path, "r") as f:
                mem = json.load(f)
            if "active_context" not in mem:
                mem["active_context"] = {}
            # 只在 stress / positive 期注入
            if phase_name in ("stress", "positive"):
                mem["active_context"]["input_pressure"] = {
                    "valence": val_inj, "arousal": aro_inj,
                    "applied_at": time.time(), "applied_at_tick": tick,
                }
            else:
                mem["active_context"]["input_pressure"] = None
            with open(mem_path, "w") as f:
                json.dump(mem, f)

        # 跑一拍
        result = le.environment_tick(force=True)
        tick += 1
        phase_tick += 1

        # 读状态
        if os.path.exists(mem_path):
            with open(mem_path, "r") as f:
                mem = json.load(f)
            rs = mem.get("self_model", {}).get("ring_state", {})
            deceased = rs.get("deceased", False)
            E_trace.append(rs.get("E", 0.5))

            # 按阶段存储
            if phase_name not in phase_metrics:
                phase_metrics[phase_name] = {"E": [], "T": [], "N": [], "energy": []}
            phase_metrics[phase_name]["E"].append(rs.get("E", 0.5))
            phase_metrics[phase_name]["T"].append(rs.get("T", 0.0))
            phase_metrics[phase_name]["N"].append(rs.get("N", 0.5))
            phase_metrics[phase_name]["energy"].append(rs.get("energy", 1.0))

            if deceased:
                alive = False
                survival_ticks = tick
                break

        # 推进到下一阶段
        if phase_tick >= TEST_PHASES[current_phase_idx][1]:
            current_phase_idx += 1
            phase_tick = 0

    if alive:
        survival_ticks = tick

    # ── 计算三维度 ──

    # 1. 生存分（长寿度）
    survival_score = survival_ticks / TOTAL_TEST_TICKS

    # 2. 稳定性（气候方差的倒数）
    if len(E_trace) > 1:
        mean_E = sum(E_trace) / len(E_trace)
        var_E = sum((x - mean_E)**2 for x in E_trace) / len(E_trace)
        # 归一化：方差=0 → 1.0；方差=1.0 → 接近 0
        stability_score = 1.0 / (1.0 + var_E * 10.0)
    else:
        stability_score = 0.0

    # 3. 响应性（平静期 E 均值 vs 压力期 E 均值的差异绝对值）
    calm_E = phase_metrics.get("calm", {}).get("E", [])
    stress_E = phase_metrics.get("stress", {}).get("E", [])
    if calm_E and stress_E:
        cal_mean = sum(calm_E) / len(calm_E)
        stress_mean = sum(stress_E) / len(stress_E)
        response_score = min(abs(stress_mean - cal_mean) / 0.3, 1.0)
    else:
        response_score = 0.0

    fitness = (W_SURVIVAL * survival_score +
               W_STABILITY * stability_score +
               W_RESPONSE * response_score)

    return {
        "survival": survival_score,
        "stability": stability_score,
        "response": response_score,
        "fitness": fitness,
        "ticks": survival_ticks,
        "alive_at_end": alive,
    }

# ────────────────────────────────────────────
# 主进化循环
# ────────────────────────────────────────────
def evolve(pop_size=16, n_generations=10, elite_ratio=0.5, mutation_scale=0.2):
    """
    主进化流程
    """
    base = get_base_genome()
    print(f"== 洛神参数基因组达尔文式进化实验 ==")
    print(f"种群大小: {pop_size}, 代数: {n_generations}")
    print(f"基因组参数: {len(GENOME_KEYS)} 个")
    print(f"测试拍数: {TOTAL_TEST_TICKS} (平静→压力→恢复→正向)")
    print(f"基线适应度将在第 0 代首次测量\n")

    # 初始化种群
    population = [mutate_genome(base, scale=0.3) for _ in range(pop_size)]
    # 保留一个基线个体（不突变）
    population[0] = copy.deepcopy(base)

    history = []  # [{gen, best_fitness, avg_fitness, best_genome}]
    all_results = []

    for gen in range(n_generations):
        print(f"\n--- 第 {gen} 代 ---")
        results = []

        for i, genome in enumerate(population):
            res = run_individual(genome, uid=f"g{gen}_i{i}")
            results.append(res)
            status = 'alive' if res['alive_at_end'] else f'died@{res["ticks"]}'
            print(f"  [{i:2d}] survival={res['survival']:.3f} "
                  f"stability={res['stability']:.3f} response={res['response']:.3f} "
                  f"→ fitness={res['fitness']:.4f}  ({status})")
            all_results.append({"gen": gen, "idx": i, **res})

        # 排序
        indices = list(range(len(population)))
        indices.sort(key=lambda i: results[i]["fitness"], reverse=True)

        best_idx = indices[0]
        best_fitness = results[best_idx]["fitness"]
        avg_fitness = sum(r["fitness"] for r in results) / len(results)

        print(f"  最佳: individual #{best_idx}, fitness={best_fitness:.4f}")
        print(f"  平均: {avg_fitness:.4f}")

        history.append({
            "gen": gen,
            "best_fitness": best_fitness,
            "avg_fitness": avg_fitness,
            "best_genome": copy.deepcopy(population[best_idx]),
            "results": results,
        })

        if gen == n_generations - 1:
            break  # 最后一代不繁殖

        # ── 选择 + 繁殖 ──
        n_elite = max(2, int(pop_size * elite_ratio))
        elites = [copy.deepcopy(population[i]) for i in indices[:n_elite]]

        # 新种群 = 精英 + 交叉变异后代
        new_population = elites[:]

        while len(new_population) < pop_size:
            p1 = random.choice(elites)
            p2 = random.choice(elites)
            child = crossover_genome(p1, p2)
            child = mutate_genome(child, scale=mutation_scale)
            new_population.append(child)

        population = new_population[:pop_size]

    return history, all_results


def save_results(history, all_results, output_path):
    """保存结果到 JSON"""
    output = {
        "meta": {
            "genome_keys": GENOME_KEYS,
            "base_genome": get_base_genome(),
            "test_phases": TEST_PHASES,
            "weights": {"survival": W_SURVIVAL, "stability": W_STABILITY, "response": W_RESPONSE},
            "total_test_ticks": TOTAL_TEST_TICKS,
            "pop_size": len(history[0]["results"]),
            "n_generations": len(history),
            "timestamp": time.time(),
        },
        "history": history,
        "all_results": all_results,
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {output_path}")


def print_summary(history):
    """打印进化轨迹摘要"""
    print(f"\n{'='*60}")
    print(f"进化轨迹")
    print(f"{'='*60}")
    print(f"{'代':>4} {'最佳':>8} {'平均':>8} {'最佳者构成'}")
    print(f"{'-'*60}")

    for h in history:
        g = h["gen"]
        bf = h["best_fitness"]
        af = h["avg_fitness"]
        bg = h["best_genome"]
        # 显示哪些参数相对基线变化超过 50%
        base = get_base_genome()
        changes = []
        for k in GENOME_KEYS:
            if base[k] != 0:
                r = bg[k] / base[k]
                if abs(r - 1.0) > 0.5:
                    changes.append(f"{k}: {r:.2f}x")
        print(f"{g:4d} {bf:8.4f} {af:8.4f}  delta_params={changes}")

    # 最终涌现分析
    if len(history) >= 2:
        Δ = history[-1]["best_fitness"] - history[0]["best_fitness"]
        print(f"\n总适应度提升: {history[0]['best_fitness']:.4f} → {history[-1]['best_fitness']:.4f} (Δ={Δ:+.4f})")
    if history[-1]["best_fitness"] <= history[0]["best_fitness"]:
        print("未观察到适应度提升（所有个体早逝或参数在测试中无分化）")
    print(f"{'='*60}")


# ────────────────────────────────────────────
# 入口
# ────────────────────────────────────────────
if __name__ == "__main__":
    random.seed(int(time.time() * 1000) % 2**32)
    history, all_results = evolve(
        pop_size=16,
        n_generations=10,
        elite_ratio=0.5,
        mutation_scale=0.2,
    )
    output_path = "experiment/evolution_result.json"
    save_results(history, all_results, output_path)
    print_summary(history)

    # 最终报告：打印最佳基因组
    best = history[-1]["best_genome"]
    base = get_base_genome()
    print(f"\n最佳基因组 (最终代):")
    for k in GENOME_KEYS:
        r = best[k] / base[k] if base[k] != 0 else float("inf")
        flag = "⬆" if r > 1.5 else ("⬇" if r < 0.5 else "≈")
        print(f"  {k:35s}: {base[k]:10.6f} → {best[k]:10.6f} ({r:.2f}x) {flag}")
