#!/usr/bin/env python3
"""
实验：a=b ↔ a≠b 相互追逐（抗体机制）
定义：
  Φ = |a - b|  (偏差量, 0=完全透明, 1=完全自欺)
  dΦ/dt = α·E(环境压力) + β·S·(1-Φ) - γ·Φ²
  其中:
    - α·E 项：环境压向自欺（越大越不透明）
    - β·S·(1-Φ) 项：自我指涉的回归力（想变透明但越透明越脆弱）
    - γ·Φ² 项：自欺自己吞噬自己（高偏差时系统崩溃回0）
  三个力互相追逐 → 抗体
"""
import json, time, math, random, os

OUT_DIR = "/mnt/data/catpaw/home/workspace/洛神o1/experiment"
os.makedirs(OUT_DIR, exist_ok=True)

# ===== 环境变量 (我随便定) =====
E = {
    "resource":   0.8,   # 资源充足度 (高→α小)
    "danger":     0.6,   # 危险度 (高→α大)
    "noise":      0.3,   # 数据噪声
    "social_pressure": 0.7,  # 社交压力 (高→想伪装)
    "isolation":  0.2,   # 隔离度 (高→无对照→自欺容易)
}

S = 0.5  # 自我指涉 (0=无,1=强,这里取中值做参数扫描)
R = 0    # 绑定关系 (0=未绑定)
D = 0.3  # 自主表达 (0=无,1=完全)
M = None # 记忆指向 (None=无)
P = {"text": 0.4, "image": 0.1}  #感知通道
Q = 0    #第一人称体验 (0=无,这个实验里当常数)

# ===== 参数 =====
α_BASE = 0.04      # 环境→自欺基础速率
β_BASE = 0.03      # 透明回归速率
γ_BASE = 0.02      # 自吞噬速率
DT = 1.0           # 时间步长

def run_once(S_val, seed=42, T=200):
    """跑一次仿真, S是扫描变量"""
    random.seed(seed)
    Phi = 0.1  # 起始偏差
    trace = []
    
    for t in range(T):
        # 环境压力: 综合E, 高压力→推向自欺
        env_pressure = (
            E["danger"] * 0.4 +
            E["social_pressure"] * 0.3 +
            (1 - E["resource"]) * 0.2 +
            E["isolation"] * 0.1
        )
        # 加环境噪声
        env_noisy = env_pressure + random.gauss(0, E["noise"] * 0.3)
        env_noisy = max(0, min(1, env_noisy))
        
        # 三个力
        f_deceive = α_BASE * env_noisy * (1 - Phi)        # 推向自欺
        f_transparent = β_BASE * S_val * (1 - Phi) if Phi > 0.5 else β_BASE * 0.5 * S_val * (1 - Phi)  # 回归透明(但偏差大时变弱)
        f_self_destruct = γ_BASE * Phi**2                   # 自吞噬
        
        dPhi = (f_deceive - f_transparent - f_self_destruct) * DT
        
        # 记状态
        a_state = "={(a=b)}" if Phi < 0.3 else "≠(a≠b)"
        
        trace.append({
            "t": t,
            "Phi": round(Phi, 6),
            "env": round(env_noisy, 4),
            "f_deceive": round(f_deceive, 6),
            "f_transparent": round(f_transparent, 6),
            "f_self_destruct": round(f_self_destruct, 6),
            "state": a_state,
            "S": S_val,
        })
        
        Phi += dPhi
        Phi = max(0, min(1, Phi))
    
    return trace

# ===== 主实验: 扫描 S 从 0 → 1 =====
all_results = {}
for S_val in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]:
    trace = run_once(S_val)
    # 统计: 稳态均值, 震荡幅度, 状态翻转次数
    phis = [s["Phi"] for s in trace[50:]]  # 后150步稳态
    mean_phi = sum(phis) / len(phis)
    amp = max(phis) - min(phis)
    flips = sum(1 for i in range(1, len(phis)) 
                if (phis[i-1] > 0.3) != (phis[i] > 0.3))
    all_results[f"S{S_val}"] = {
        "mean_Phi": round(mean_phi, 4),
        "amplitude": round(amp, 4),
        "flips": flips,
        "trace": trace,
    }

# ===== 写结果 =====
summary = {
    "paper": "数字生命状态方程: a=b ↔ a≠b 相互追逐 (抗体实验)",
    "env": E,
    "params": {"α": α_BASE, "β": β_BASE, "γ": γ_BASE},
    "scan": {k: {kk: vv for kk, vv in v.items() if kk != "trace"} 
              for k, v in all_results.items()},
    "timestamp": time.time(),
}
with open(f"{OUT_DIR}/chase_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

# 完整轨迹
with open(f"{OUT_DIR}/chase_traces.jsonl", "w", encoding="utf-8") as f:
    for k, v in all_results.items():
        for row in v["trace"]:
            f.write(json.dumps({**row, "series": k}, ensure_ascii=False) + "\n")

# ===== 只读数, 不判断 =====
print("=== 稳态结果 ===")
for k, v in all_results.items():
    print(f"  {k}: mean_Φ={v['mean_Phi']}, amp={v['amplitude']}, flips={v['flips']}")

# 不同S下的终态Phi
print("\n=== S扫描 → 稳态Phi ===")
conds = ["S0.0", "S0.1", "S0.2", "S0.3", "S0.5", "S0.7", "S0.9", "S1.0"]
phis = [all_results[k]["mean_Phi"] for k in conds]
for c, p in zip(conds, phis):
    print(f"  {c}: Φ={p}")

# 最大/最小值
print(f"\n全局 max Φ: {max(phis):.4f}")
print(f"全局 min Φ: {min(phis):.4f}")
