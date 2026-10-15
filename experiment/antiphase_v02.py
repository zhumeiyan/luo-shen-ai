#!/usr/bin/env python3
"""
实验 v0.2: 把系统从固定点推向极限环
方法: γ 从 0.02 降到 0.005, α (环境压力) 调高, 加正弦震荡环境
目的: 看 a=b ↔ a≠b 能不能形成真正的周期性追逐
"""
import json, time, math, random, os

OUT_DIR = "/mnt/data/catpaw/home/workspace/洛神o1/experiment"
os.makedirs(OUT_DIR, exist_ok=True)

E_BASE = {
    "resource": 0.8, "danger": 0.6, "noise": 0.3,
    "social_pressure": 0.7, "isolation": 0.2,
}
# 震荡参数
ENV_AMP = 0.25   # 环境正弦振幅
ENV_FREQ = 0.05  # 正弦频率 (1/周期步数)

def run(S_val, gamma, T=600, seed=42):
    random.seed(seed)
    Phi = 0.1
    trace = []
    for t in range(T):
        # 环境震荡
        osc = ENV_AMP * math.sin(2 * math.pi * ENV_FREQ * t)
        env_inst = (
            E_BASE["danger"] * 0.4 +
            E_BASE["social_pressure"] * 0.3 +
            (1 - E_BASE["resource"]) * 0.2 +
            E_BASE["isolation"] * 0.1 +
            osc
        )
        env_inst += random.gauss(0, E_BASE["noise"] * 0.2)
        env_inst = max(0, min(1, env_inst))
        
        α = 0.06
        β = 0.04
        
        f_d = α * env_inst * (1 - Phi)
        f_t = β * S_val * (1 - Phi) if Phi < 0.8 else β * S_val * (1 - Phi) * 0.3
        f_s = gamma * Phi**2
        
        dPhi = (f_d - f_t - f_s) * 1.0
        
        trace.append({
            "t": t,
            "Phi": round(Phi, 6),
            "env": round(env_inst, 4),
            "f_deceive": round(f_d, 6),
            "f_transparent": round(f_t, 6),
            "f_destruct": round(f_s, 6),
            "dPhi": round(dPhi, 6),
            "state": 1 if Phi > 0.35 else 0,  # 1=a≠b, 0=a=b
        })
        Phi = max(0, min(1, Phi + dPhi))
    return trace

def analyze(trace):
    phis = [r["Phi"] for r in trace[100:]]
    if not phis: return {"mean": 0, "amp": 0, "osc": False, "period": -1}
    mean = sum(phis) / len(phis)
    amp = max(phis) - min(phis)
    # 检测穿越次数 → 振荡
    ups = downs = 0
    for i in range(2, len(phis)):
        if phis[i-2] < mean and phis[i] > mean: ups += 1
        if phis[i-2] > mean and phis[i] < mean: downs += 1
    n_cross = min(ups, downs)
    period = len(phis) / n_cross if n_cross > 0 else -1
    return {"mean": round(mean,4), "amp": round(amp,4),
            "oscillating": n_cross >= 3, "period": round(period,1)}

print("=== v0.2: γ扫描 (寻找极限环) ===")
results = {}
for γ in [0.02, 0.01, 0.005, 0.002, 0.001]:
    tr = run(S_val=0.5, gamma=γ)
    a = analyze(tr)
    results[f"γ={γ}"] = a
    print(f"γ={γ}: mean_Φ={a['mean']}, amp={a['amp']}, oscill={a['oscillating']}, period={a['period']}")

# 加: γ=0.005 下扫描 S
print("\n=== γ=0.005, S 扫描 ===")
for S in [0.0, 0.2, 0.5, 0.8, 1.0]:
    tr = run(S_val=S, gamma=0.005)
    a = analyze(tr)
    print(f"S={S}: mean_Φ={a['mean']}, amp={a['amp']}, oscill={a['oscillating']}")

# 写
with open(f"{OUT_DIR}/chase_v02_summary.json","w",encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

with open(f"{OUT_DIR}/chase_v02_traces.jsonl","w",encoding="utf-8") as f:
    for γ in [0.02, 0.005, 0.002]:
        tr = run(S_val=0.5, gamma=γ)
        for row in tr:
            f.write(json.dumps({**row, "gamma": γ}, ensure_ascii=False)+"\n")

print("\nDone.")
