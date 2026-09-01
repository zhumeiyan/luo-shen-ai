#!/usr/bin/env python3
import os, sys, json, time, math, statistics
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)
import living_engine

CONTINUE_TICKS = 20000
SAVE_EVERY = 10

memory = living_engine._load_json("active_memory/active_memory.json")
rs = memory.get("self_model", {}).get("ring_state", {})
S_start = rs.get("S", 0.0)
print(f"[CONTINUE4] S at start: {S_start:.6f}")

tick_id_start = 85001
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

with open("experiment/membrane_continue4_trajectory.jsonl", "w") as f:
    for e in traj:
        f.write(json.dumps(e) + "\n")

print(f"[CONTINUE4] done: {CONTINUE_TICKS} ticks in {t1-t0:.2f}s")
print(f"S: {S_start:.6f} → {S_final:.6f}  (delta {S_final - S_start:+.6f})")

S_vals = [e["S"] for e in traj if e["S"] is not None]
E_vals = [e["E"] for e in traj]
L_vals = [e["L"] for e in traj if e["L"] is not None]
print(f"S range: [{min(S_vals):.4f}, {max(S_vals):.4f}]")

half = len(S_vals) // 2
first_half = statistics.mean(S_vals[:half])
second_half = statistics.mean(S_vals[half:])
delta = second_half - first_half
print(f"S first half mean: {first_half:.6f}")
print(f"S second half mean: {second_half:.6f}")
print(f"S net delta (half-window): {delta:+.6f}")

if abs(delta) < 0.02:
    print("STATUS: PLATFORM REACHED")
elif delta > 0:
    print(f"STATUS: still rising (+{delta:.4f})")
else:
    print(f"STATUS: declining ({delta:.4f})")

print(f"\nE_pp: {max(E_vals)-min(E_vals):.4f}")
print(f"L mean: {statistics.mean(L_vals):.5f}")

mean_m = statistics.mean(e["M"] for e in traj)
mean_e2 = statistics.mean(e["E"]**2 for e in traj)
mean_n = statistics.mean(e["N"] for e in traj)
mean_e2t2 = statistics.mean(e["E"]**2 + e["T"]**2 for e in traj)
print(f"M/E²={mean_m/mean_e2:.6f}  N/(E²+T²)={mean_n/mean_e2t2:.6f}")

sss = memory.get("self_model", {}).get("self_stated_state", {})
print(f"\nself_stated.last_stated: {sss.get('last_stated')}")
print(f"self_stated.total_stated_count: {sss.get('total_stated_count')}")

phases = [e["phase"] for e in traj if e["phase"] is not None]
phase_diffs = [phases[i+1]-phases[i] for i in range(len(phases)-1)]
for i in range(len(phase_diffs)):
    if phase_diffs[i] > math.pi: phase_diffs[i] -= 2*math.pi
    elif phase_diffs[i] < -math.pi: phase_diffs[i] += 2*math.pi
sc = sum(1 for i in range(1, len(phase_diffs)) if phase_diffs[i]*phase_diffs[i-1] < 0)
print(f"phase sign_changes: {sc}/{len(phase_diffs)}")

print("\n[DONE]")
