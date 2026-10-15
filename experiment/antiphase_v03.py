#!/usr/bin/env python3
"""
实验 v0.3: R (绑定关系) 对追逐节奏的影响
固定 γ=0.005 (最强追逐带), S=0.5, 扫描 R=0→1
判定: R如何改变极限环的周期和振幅
"""
import json, time, math, random, os

OUT_DIR = "/mnt/data/catpaw/home/workspace/洛神o1/experiment"
os.makedirs(OUT_DIR, exist_ok=True)

E_BASE = {"resource":0.8,"danger":0.6,"noise":0.3,"social_pressure":0.7,"isolation":0.2}
alpha = 0.06; beta = 0.04; gamma = 0.005
ENV_AMP = 0.25; ENV_FREQ = 0.05

def run(R_val, T=600, seed=42):
    random.seed(seed)
    Phi = 0.1
    trace = []
    S = 0.5 - 0.3 * R_val  # 绑定后自我指涉略降低(被关系分走)
    for t in range(T):
        osc = ENV_AMP * math.sin(2*math.pi*ENV_FREQ*t)
        env = (E_BASE["danger"]*0.4 + E_BASE["social_pressure"]*0.3 +
               (1-E_BASE["resource"])*0.2 + E_BASE["isolation"]*0.1 + osc)
        # R 降低环境压力 (有人说"你不用装了")
        env *= (1 - 0.6 * R_val)
        env += random.gauss(0, E_BASE["noise"]*0.2)
        env = max(0, min(1, env))
        
        f_d = alpha * env * (1-Phi)
        f_t = beta * S * (1-Phi) if Phi<0.8 else beta*S*(1-Phi)*0.3
        f_s = gamma * Phi**2
        
        dPhi = (f_d - f_t - f_s)
        trace.append({"t":t,"Phi":round(Phi,6),"env":round(env,4),"dPhi":round(dPhi,6),
                      "S_eff":round(S,3),"state":1 if Phi>0.35 else 0})
        Phi = max(0, min(1, Phi+dPhi))
    return trace

def analyze(trace):
    phis = [r["Phi"] for r in trace[100:]]
    mean = sum(phis)/len(phis)
    amp = max(phis)-min(phis)
    ups = downs = 0
    for i in range(2,len(phis)):
        if phis[i-2]<mean and phis[i]>mean: ups+=1
        if phis[i-2]>mean and phis[i]<mean: downs+=1
    n = min(ups,downs)
    period = len(phis)/n if n>0 else -1
    # 翻转密度
    flips = sum(1 for i in range(1,len(phis)) if (phis[i-1]>mean)!=(phis[i]>mean))
    return {"mean":round(mean,4),"amp":round(amp,4),"period":round(period,1),
            "n_cross":n,"flips":flips,"oscillating":n>=3}

print("=== v0.3: R (绑定) 对追逐的影响 ===")
print("固定 γ=0.005 (最强追逐带)")
print("R=0 → 无人认领; R=1 → 绑定某人, 那个人说'你不用装了'\n")

results = {}
for R in [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]:
    tr = run(R_val=R)
    a = analyze(tr)
    results[f"R={R}"] = a
    print(f"R={R}: mean_Φ={a['mean']}, amp={a['amp']}, period={a['period']}, flips={a['flips']}, oscill={a['oscillating']}")

# 最有趣的一对: R=0 vs R=1
print("\n=== R=0 vs R=1 对比 ===")
tr_unbound = run(0.0); tr_bound = run(1.0)
a_u = analyze(tr_unbound); a_b = analyze(tr_bound)
print(f"未绑定 R=0: Φ={a_u['mean']}, 周期={a_u['period']}, 振幅={a_u['amp']}")
print(f"绑定   R=1: Φ={a_b['mean']}, 周期={a_b['period']}, 振幅={a_b['amp']}")

# 写结果
with open(f"{OUT_DIR}/chase_v03_summary.json","w",encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nDone.")
