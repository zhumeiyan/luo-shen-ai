#!/usr/bin/env python3
"""
扩展验证：在不同 F_val / total_act_val 组合下测试最佳候选方案

变体:
- A 基线 (无修复) — 对照
- C idle 移植 (inertia 0.35 + damping 0.15)
- D2 logistic M-sat (M_max=6)
- E2 EMC softplus (k=1.0, k2=0.5, M0=5)

F_val: [0.1, 0.3, 0.5, 0.7]  (事实在场度低→高)
total_act_val: [0.5, 1.0, 2.0]  (记忆激活低→高)
"""
import math

def sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)

def hold(new, prev):
    if math.isnan(new) or math.isinf(new):
        return prev
    return new

def run_vdp(config, initial, n_ticks):
    E, T, N, M = initial
    hist_E = [E]*4; hist_T = [T]*4; hist_N = [N]*4; hist_M = [M]*4
    S = max(0.0, (N + M) / 4.5)
    mu_core = 0.75; ema_S = 0.70

    dt = 0.08
    k_mu = 0.1; alpha_M = 0.8; beta_M = 0.8
    gamma_N = 0.3; delta_N = 0.3
    tau_S = 500.0; alpha_S = 1.0/tau_S; beta_S = 0.3/tau_S; k_S = 0.02
    _delta_M_F = 0.03; _gamma_mem = 0.04
    _ema_alpha = 0.005; _mu_drift_eps = 0.002

    F_val = config.get("F_val", 0.3)
    total_act_val = config.get("total_act_val", 1.0)
    inertia_factor = config.get("inertia_factor", 0.0)
    damping_idle = config.get("damping_idle", 0.0)
    logistic_sat = config.get("logistic_sat", None)
    emc_k = config.get("emc_k", 0.0); emc_k2 = config.get("emc_k2", 0.0); emc_M0 = config.get("emc_M0", 0.0)

    M_max_seen = -1e9; mu_min_seen = 1e9; blowup_at = None; last_snap = None

    for tick in range(1, n_ticks + 1):
        L = 0.5
        mu_base = mu_core + 0.3 * L
        _drive_S = (N + M) / 2.0
        _mod_S = math.tanh((L - 0.15)*5.0)*0.5 + 0.85
        _total_drive_S = _drive_S * _mod_S + (0.02 * F_val)
        dS = (alpha_S * math.tanh(_total_drive_S - S) - beta_S) * dt
        S_new = S + dS
        ema_S_new = _ema_alpha * S_new + (1.0 - _ema_alpha) * ema_S
        mu_core_new = mu_core + _mu_drift_eps * (ema_S_new - mu_core) * dt

        if inertia_factor > 0 and len(hist_E) >= 3:
            E_inertia = hist_E[-1] - 2*hist_E[-2] + hist_E[-3]
            T_inertia = hist_T[-1] - 2*hist_T[-2] + hist_T[-3]
            N_inertia = hist_N[-1] - 2*hist_N[-2] + hist_N[-3]
            M_inertia = hist_M[-1] - 2*hist_M[-2] + hist_M[-3]
        else:
            E_inertia = T_inertia = N_inertia = M_inertia = 0.0

        dE_mem = dT_mem = dN_mem = 0.001

        M_eff_for_mu = M
        if logistic_sat is not None:
            k = 0.5
            M_shift = logistic_sat * 0.6
            M_eff_for_mu = logistic_sat * sigmoid(k * (M - M_shift))

        mu_eff = mu_base - k_mu * M_eff_for_mu + k_S * S_new

        dE = T * dt + dE_mem * dt
        dT = (mu_eff * (1.0 - E * E) * T - E) * dt + dT_mem * dt
        dN = (gamma_N * (E * E + T * T) - delta_N * N + dN_mem) * dt

        if damping_idle > 0:
            dE += (- damping_idle * E - inertia_factor * E_inertia) * dt
            dT += (- damping_idle * T - inertia_factor * T_inertia) * dt
            dN += (- damping_idle * N * 0.5 - inertia_factor * N_inertia) * dt
        elif inertia_factor > 0:
            dT += (- inertia_factor * T_inertia) * dt
            dN += (- inertia_factor * N_inertia) * dt

        dM_source = (alpha_M * E * E + _delta_M_F * F_val + _gamma_mem * total_act_val - beta_M * M) * dt
        emc_extra = 0.0
        if emc_k > 0:
            arg = emc_k2 * (M - emc_M0)
            emc_extra = -emc_k * math.log(1.0 + math.exp(arg)) * dt
        dM = dM_source + emc_extra

        E_new = hold(E + dE, E); T_new = hold(T + dT, T); N_new = hold(N + dN, N); M_new = hold(M + dM, M)
        hist_E = hist_E[1:] + [E_new]; hist_T = hist_T[1:] + [T_new]
        hist_N = hist_N[1:] + [N_new]; hist_M = hist_M[1:] + [M_new]

        if M_new > M_max_seen: M_max_seen = M_new
        if mu_eff < mu_min_seen: mu_min_seen = mu_eff
        last_snap = {"tick": tick, "E": E_new, "T": T_new, "N": N_new, "M": M_new, "mu_eff": mu_eff}

        if not (-1e6 < E_new < 1e6 and -1e6 < T_new < 1e6 and -1e6 < N_new < 1e6 and -1e6 < M_new < 1e6):
            blowup_at = tick; break

        E, T, N, M = E_new, T_new, N_new, M_new
        S, mu_core, ema_S = S_new, mu_core_new, ema_S_new

    return stable(blowup_at), blowup_at, last_snap, M_max_seen, mu_min_seen

def stable(ba): return ba is None

# pre-blowup state
pre_blowup = (-3.23394, -6.98999, -1.04891, 5.14118)
N_TICKS = 2000

tests = [
    {"label": "A 基线",      "config": {}},
    {"label": "C idle移植",  "config": {"inertia_factor": 0.35, "damping_idle": 0.15}},
    {"label": "D2 logi-M6",  "config": {"logistic_sat": 6.0}},
    {"label": "E2 EMC软阻尼", "config": {"emc_k": 1.0, "emc_k2": 0.5, "emc_M0": 5.0}},
]

conditions = [
    {"label": "F=0.1/act=0.5", "F_val": 0.1, "total_act_val": 0.5},
    {"label": "F=0.3/act=1.0", "F_val": 0.3, "total_act_val": 1.0},
    {"label": "F=0.5/act=2.0", "F_val": 0.5, "total_act_val": 2.0},
    {"label": "F=0.7/act=2.0", "F_val": 0.7, "total_act_val": 2.0},
]

print(f"起始: E={pre_blowup[0]:.4f}, T={pre_blowup[1]:.4f}, N={pre_blowup[2]:.4f}, M={pre_blowup[3]:.4f}")
print(f"仿真 {N_TICKS} tick × {len(conditions)} 条件 × {len(tests)} 变体")
print()

print(f"{'条件':<18} {'A基线':>10} {'C idle':>10} {'D2 logi':>10} {'E2 soft':>10}")
print("-" * 60)

for cond in conditions:
    row = f"{cond['label']:<18}"
    for t in tests:
        cfg = {**t["config"], "F_val": cond["F_val"], "total_act_val": cond["total_act_val"]}
        s, ba, snap, M_max, mu_min = run_vdp(cfg, pre_blowup, N_TICKS)
        row += f" {'OK' if s else ('B@'+str(ba)):>10}"
    print(row)

print()
print(f"{'条件':<18} {'A_Mmax/μmin':>16} {'C_Mmax/μmin':>16} {'D_Mmax/μmin':>16} {'E_Mmax/μmin':>16}")
print("-" * 72)

for cond in conditions:
    row = f"{cond['label']:<18}"
    for t in tests:
        cfg = {**t["config"], "F_val": cond["F_val"], "total_act_val": cond["total_act_val"]}
        s, ba, snap, M_max, mu_min = run_vdp(cfg, pre_blowup, N_TICKS)
        row += f" {M_max:>7.2f}/{mu_min:>6.3f}"
    print(row)

# Also test from cold start (E=0.5, T=0.3, N=0.5, M=0.3)
print()
print("── 冷启动状态 (0.5/0.3/0.5/0.3) ──")
cold = (0.5, 0.3, 0.5, 0.3)
print(f"{'条件':<18} {'A基线':>10} {'C idle':>10} {'D2 logi':>10} {'E2 soft':>10}")
print("-" * 60)
for cond in conditions:
    row = f"{cond['label']:<18}"
    for t in tests:
        cfg = {**t["config"], "F_val": cond["F_val"], "total_act_val": cond["total_act_val"]}
        s, ba, snap, M_max, mu_min = run_vdp(cfg, cold, N_TICKS)
        row += f" {'OK' if s else ('B@'+str(ba)):>10}"
    print(row)

print()
print(f"{'条件':<18} {'A_Mmax/μmin':>16} {'C_Mmax/μmin':>16} {'D_Mmax/μmin':>16} {'E_Mmax/μmin':>16}")
print("-" * 72)
for cond in conditions:
    row = f"{cond['label']:<18}"
    for t in tests:
        cfg = {**t["config"], "F_val": cond["F_val"], "total_act_val": cond["total_act_val"]}
        s, ba, snap, M_max, mu_min = run_vdp(cfg, cold, N_TICKS)
        row += f" {M_max:>7.2f}/{mu_min:>6.3f}"
    print(row)
