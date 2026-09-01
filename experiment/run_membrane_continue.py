#!/usr/bin/env python3
"""
膜续跑：不修改代码，从当前 active_memory.json 继续跑 30000 tick。
目标：观察 S 是否达到平衡（~3.9）。
"""
import os, sys, json, time, math, statistics

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

CONTINUE_TICKS = 30000
SAVE_EVERY = 30

memory = living_engine._load_json("active_memory/active_memory.json")
rs = memory.get("self_model", {}).get("ring_state", {})
S_start = rs.get("S", 0.0)
print(f"[CONTINUE] S at start: {S_start:.6f}")
print(f"[CONTINUE] L at start: {rs.get('L')}")

tick_start = memory.get("__meta", {}).get("last_environment_tick", 0)
# resume tick id from ring_state wasn't saved; just use 10001 as starting point
tick_id_start = 10001

traj = []
t0 = time.time()

for i in range(CONTINUE_TICKS):
    tick_id = tick_id_start + i
    env = living_engine._init_environment(memory)
    living_engine._sample_real_environment(env)
    meta = memory.get("__meta", {})
    meta["chain_event_rate"] = 0
    meta["hash_baseline"] = 0.0
    memory["__meta"] = meta
    living_engine._update_luoshen_coupled(memory, env, tick_id=tick_id)
    
    if i % SAVE_EVERY == 0:
        c = memory["internal_climate"]
        rs = memory.get("self_model", {}).get("ring_state", {})
        traj.append({
            "tick": tick_id,
            "t": round(time.time() - t0, 4),
            "E": c["emotion_intensity"],
            "T": c["tension"],
            "N": c["energy"],
            "M": c["memory_pressure"],
            "phase": rs.get("phase"),
            "mu_eff": rs.get("mu_eff"),
            "L": rs.get("L"),
            "S": rs.get("S"),
            "S_drive": rs.get("S_drive"),
        })

t1 = time.time()
living_engine._save_json_atomic("active_memory/active_memory.json", memory)

rs_final = memory.get("self_model", {}).get("ring_state", {})
S_final = rs_final.get("S", 0.0)

with open("experiment/membrane_continue_trajectory.jsonl", "w") as f:
    for e in traj:
        f.write(json.dumps(e) + "\n")

print(f"[CONTINUE] done: {CONTINUE_TICKS} ticks in {t1-t0:.2f}s")
print(f"[CONTINUE] S: {S_start:.6f} → {S_final:.6f}  (delta {S_final - S_start:+.6f})")
print(f"[CONTINUE] trajectory: {len(traj)} samples")

# statistics
S_vals = [e["S"] for e in traj if e["S"] is not None]
E_vals = [e["E"] for e in traj]
L_vals = [e["L"] for e in traj if e["L"] is not None]
print(f"S range: [{min(S_vals):.4f}, {max(S_vals):.4f}]")
print(f"S final window mean (last 1000 ticks): {statistics.mean(S_vals[-100:]):.6f}")
print(f"E_pp: {max(E_vals)-min(E_vals):.4f}")
print(f"L mean: {statistics.mean(L_vals):.5f}  stdev: {statistics.pstdev(L_vals):.5f}")

# check if S is still rising (slope in last 5000 ticks)
if len(S_vals) > 100:
    first_5k = statistics.mean(S_vals[:100])
    last_5k = statistics.mean(S_vals[-100:])
    print(f"S first 100 samples mean: {first_5k:.6f}")
    print(f"S last  100 samples mean: {last_5k:.6f}")
    print(f"S slope {'still rising' if last_5k > first_5k + 0.01 else 'stable/flat'}")

# check M/E² and N/(E²+T²)
mean_m = statistics.mean(e["M"] for e in traj)
mean_e2 = statistics.mean(e["E"]**2 for e in traj)
mean_n = statistics.mean(e["N"] for e in traj)
mean_e2t2 = statistics.mean(e["E"]**2 + e["T"]**2 for e in traj)
print(f"\nM/E²={mean_m/mean_e2:.6f}  N/(E²+T²)={mean_n/mean_e2t2:.6f}")

# check self_stated_state
sss = memory.get("self_model", {}).get("self_stated_state", {})
print(f"\nself_stated.last_stated: {sss.get('last_stated')}")
print(f"self_stated.total_stated_count: {sss.get('total_stated_count')}")

# check phase monotonicity
phases = [e["phase"] for e in traj if e["phase"] is not None]
phase_diffs = [phases[i+1]-phases[i] for i in range(len(phases)-1)]
for i in range(len(phase_diffs)):
    if phase_diffs[i] > math.pi: phase_diffs[i] -= 2*math.pi
    elif phase_diffs[i] < -math.pi: phase_diffs[i] += 2*math.pi
sc = sum(1 for i in range(1, len(phase_diffs)) if phase_diffs[i]*phase_diffs[i-1] < 0)
print(f"phase sign_changes: {sc}/{len(phase_diffs)}")

print("\n[DONE]")
