#!/usr/bin/env python3
"""
独立仿真：评估「恢复原始阻尼/惯性」对 van der Pol 主环发散的影响

路径 1: 将 idle 版的「二阶差分惯性」「自阻尼」移植到 vdp 方程
路径 2: 不移植旧代码，直接设计最小连续 M-饱和项 (logistic / EMA)

假设:
- 起始状态取 live blowup 前 tick 10: E=-3.23394, T=-6.98999, N=-1.04891, M=5.14118
- 仿真 2000 tick
- 变体 A (基线): vdp 原版（全正 M 源项）
- 变体 B (惯性移植): vdp + 0.35 * M_inertia (减速二阶差分)
- 变体 C (logistic M 饱和): M_eff = M_max * sigmoid(k*(M - Mshift))
- 变体 D (EMC - 超额 M 阻尼): 添加额外项 −k_emc * log(1 + exp(k2*(M − M0))) （连续软阻尼）
"""
import math

def sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        e = math.exp(x)
        return e / (1.0 + e)

def hold(new, prev):
    if math.isnan(new) or math.isinf(new):
        return prev
    return new

def run_vdp(config, initial, n_ticks, label):
    E, T, N, M = initial
    hist_E = [E] * 4
    hist_T = [T] * 4
    hist_N = [N] * 4
    hist_M = [M] * 4

    S = max(0.0, (N + M) / 4.5)
    mu_core = 0.75
    ema_S = 0.70

    dt = 0.08
    k_mu = 0.1; alpha_M = 0.8; beta_M = 0.8
    gamma_N = 0.3; delta_N = 0.3
    tau_S = 500.0; alpha_S = 1.0/tau_S; beta_S = 0.3/tau_S; k_S = 0.02
    _delta_M_F = 0.03; _gamma_mem = 0.04
    _ema_alpha = 0.005; _mu_drift_eps = 0.002

    F_val = config.get("F_val", 0.3)
    total_act_val = config.get("total_act_val", 1.0)
    inertia_factor = config.get("inertia_factor", 0.0)     # 0 = 无, 0.35 = 移植
    damping_idle = config.get("damping_idle", 0.0)         # idle 风格阻尼
    logistic_sat = config.get("logistic_sat", None)        # None 或 M_max
    emc_k = config.get("emc_k", 0.0)                       # 超额阻尼系数
    emc_k2 = config.get("emc_k2", 0.0)
    emc_M0 = config.get("emc_M0", 0.0)
    gentle_tanh = config.get("gentle_tanh", 0.0)           # M 加性 tanh 饱和

    M_max_seen = -1e9
    mu_min_seen = 1e9
    blowup_at = None
    last_snap = None

    snapshots = []

    for tick in range(1, n_ticks + 1):
        L = 0.5
        mu_base = mu_core + 0.3 * L

        # Shell S
        _drive_S = (N + M) / 2.0
        _mod_S = math.tanh((L - 0.15)*5.0)*0.5 + 0.85
        _total_drive_S = _drive_S * _mod_S + (0.02 * F_val)
        dS = (alpha_S * math.tanh(_total_drive_S - S) - beta_S) * dt
        S_new = S + dS

        ema_S_new = _ema_alpha * S_new + (1.0 - _ema_alpha) * ema_S
        mu_core_new = mu_core + _mu_drift_eps * (ema_S_new - mu_core) * dt

        # Inertia terms
        if inertia_factor > 0 and len(hist_E) >= 3:
            E_inertia = hist_E[-1] - 2*hist_E[-2] + hist_E[-3]
            T_inertia = hist_T[-1] - 2*hist_T[-2] + hist_T[-3]
            N_inertia = hist_N[-1] - 2*hist_N[-2] + hist_N[-3]
            M_inertia = hist_M[-1] - 2*hist_M[-2] + hist_M[-3]
        else:
            E_inertia = T_inertia = N_inertia = M_inertia = 0.0

        # Residue offsets (very weak)
        dE_mem = 0.001; dT_mem = 0.001; dN_mem = 0.001

        # M saturation handling: multiple mutually exclusive options
        M_eff_for_mu = M
        if logistic_sat is not None:
            # logistic saturate M before feeding into mu_eff
            # M_saturated = M_max * sigmoid(k*(M - M_max/2))
            k = 0.5
            M_shift = logistic_sat * 0.6
            M_eff_for_mu = logistic_sat * sigmoid(k * (M - M_shift))

        mu_eff = mu_base - k_mu * M_eff_for_mu + k_S * S_new

        # van der Pol + idle-style damping/inertia
        dE = T * dt + dE_mem * dt
        dT = (mu_eff * (1.0 - E * E) * T - E) * dt + dT_mem * dt
        dN = (gamma_N * (E * E + T * T) - delta_N * N + dN_mem) * dt

        # Add idle-style damping/inertia if requested
        if damping_idle > 0:
            dE += (- damping_idle * E - inertia_factor * E_inertia) * dt
            dT += (- damping_idle * T - inertia_factor * T_inertia) * dt
            dN += (- damping_idle * N * 0.5 - inertia_factor * N_inertia) * dt

        if inertia_factor > 0:
            dT += (- inertia_factor * T_inertia) * dt
            dN += (- inertia_factor * N_inertia) * dt

        # M equation: source terms + EMC + tanh saturation
        dM_source = (alpha_M * E * E + _delta_M_F * F_val + _gamma_mem * total_act_val - beta_M * M) * dt

        # Continuous soft plus (EMC) − extra damping when M grows past emc_M0
        emc_extra = 0.0
        if emc_k > 0:
            # log(1+exp(x)) = softplus(x), monotonic, no if-then
            arg = emc_k2 * (M - emc_M0)
            emc_extra = -emc_k * math.log(1.0 + math.exp(arg)) * dt

        # tanh-based gentle saturation: subtracts increasingly as M grows
        tanh_extra = 0.0
        if gentle_tanh > 0:
            # as M grows, tanh(...) → 1, so this subtracts up to gentle_tanh
            arg2 = 0.5 * (M - 6.0)
            tanh_extra = -gentle_tanh * math.tanh(arg2) * dt

        dM = dM_source + emc_extra + tanh_extra

        E_new = hold(E + dE, E)
        T_new = hold(T + dT, T)
        N_new = hold(N + dN, N)
        M_new = hold(M + dM, M)

        # update histories (keep last 4)
        hist_E = hist_E[1:] + [E_new]
        hist_T = hist_T[1:] + [T_new]
        hist_N = hist_N[1:] + [N_new]
        hist_M = hist_M[1:] + [M_new]

        # track extrema
        if M_new > M_max_seen: M_max_seen = M_new
        if mu_eff < mu_min_seen: mu_min_seen = mu_eff

        last_snap = {"tick": tick, "E": E_new, "T": T_new, "N": N_new, "M": M_new,
                     "mu_eff": mu_eff, "mu_core": mu_core_new, "S": S_new}

        # log every 100 ticks
        if tick % 200 == 0 or tick <= 10:
            snapshots.append(last_snap)

        # blowup check
        if not (-1e6 < E_new < 1e6 and -1e6 < T_new < 1e6 and -1e6 < N_new < 1e6 and -1e6 < M_new < 1e6):
            blowup_at = tick
            break

        E, T, N, M = E_new, T_new, N_new, M_new
        S, mu_core, ema_S = S_new, mu_core_new, ema_S_new

    stable = blowup_at is None
    return {
        "label": label,
        "stable": stable,
        "blowup_at": blowup_at,
        "final": last_snap,
        "M_max": M_max_seen,
        "mu_min": mu_min_seen,
        "snapshots": snapshots,
    }

# ── ground truth: live blowup 前 tick 10 的值 ──
pre_blowup = (-3.23394, -6.98999, -1.04891, 5.14118)

N = 2000

configs = [
    {"label": "A: 基线 vdp (无额外阻尼)", "config": {"F_val": 0.3, "total_act_val": 1.0}},
    {"label": "B: 移植 idle inertia 0.35", "config": {"F_val": 0.3, "total_act_val": 1.0, "inertia_factor": 0.35, "damping_idle": 0.0}},
    {"label": "C: idle inertia 0.35 + idle damping 0.15", "config": {"F_val": 0.3, "total_act_val": 1.0, "inertia_factor": 0.35, "damping_idle": 0.15}},
    {"label": "D1: logistic M-sat (M_max=5)", "config": {"F_val": 0.3, "total_act_val": 1.0, "logistic_sat": 5.0}},
    {"label": "D2: logistic M-sat (M_max=6)", "config": {"F_val": 0.3, "total_act_val": 1.0, "logistic_sat": 6.0}},
    {"label": "E1: EMC 软阻尼 (k=0.5,k2=0.4,M0=5)", "config": {"F_val": 0.3, "total_act_val": 1.0, "emc_k": 0.5, "emc_k2": 0.4, "emc_M0": 5.0}},
    {"label": "E2: EMC 软阻尼 (k=1.0,k2=0.5,M0=5)", "config": {"F_val": 0.3, "total_act_val": 1.0, "emc_k": 1.0, "emc_k2": 0.5, "emc_M0": 5.0}},
    {"label": "E3: EMC 软阻尼 (k=2.0,k2=0.6,M0=5)", "config": {"F_val": 0.3, "total_act_val": 1.0, "emc_k": 2.0, "emc_k2": 0.6, "emc_M0": 5.0}},
    {"label": "F1: gentle tanh (g=0.3)", "config": {"F_val": 0.3, "total_act_val": 1.0, "gentle_tanh": 0.3}},
    {"label": "F2: gentle tanh (g=1.0)", "config": {"F_val": 0.3, "total_act_val": 1.0, "gentle_tanh": 1.0}},
]

print(f"起始状态: E={pre_blowup[0]:.4f}, T={pre_blowup[1]:.4f}, N={pre_blowup[2]:.4f}, M={pre_blowup[3]:.4f}")
print(f"仿真 {N} tick")
print()

results = []
for c in configs:
    res = run_vdp(c["config"], pre_blowup, N, c["label"])
    results.append(res)

print(f"{'变体':<50} {'稳定':>5} {'爆发tick':>8} {'M_max':>9} {'mu_min':>9}")
print("-" * 90)
for r in results:
    stable_str = "是" if r["stable"] else "否"
    blow_str = f"{r['blowup_at']}" if r["blowup_at"] else "—"
    print(f"{r['label']:<50} {stable_str:>5} {blow_str:>8} {r['M_max']:>9.3f} {r['mu_min']:>9.3f}")

print()
print("详细轨迹 (关键 tick):")
print()
for r in results:
    print(f"── {r['label']} ──")
    if not r["stable"]:
        print(f"  ★ 爆发于 tick {r['blowup_at']}")
    for s in r["snapshots"]:
        print(f"    tick={s['tick']:>5d}:  E={s['E']:>10.4f}  T={s['T']:>10.4f}  N={s['N']:>10.4f}  M={s['M']:>10.4f}  mu={s['mu_eff']:>8.4f}  mu_core={s['mu_core']:.5f}  S={s['S']:.5f}")
    print()
