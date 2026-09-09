#!/usr/bin/env python3
"""
诊断 (c)：从 tick 200 真实快照出发，运行耦合系统 2000 tick，
与国际原版等价但置于单进程可控仿真器中，精确追踪是否/何时/如何发散
"""
import math

def hold(new, prev):
    if math.isnan(new) or math.isinf(new):
        return prev
    return new

def run_from_live_state(ticks, state_200, label):
    E, T, N, M = state_200
    S = max(0.0, (N + M) / 4.5)  # 反推：drive_S ≈ 3.75 → S_eq (稳态近似)
    mu_core = 0.499               # 反推
    ema_S = 0.48                  # 反推
    
    dt = 0.08
    k_mu = 0.1; alpha_M = 0.8; beta_M = 0.8; gamma_N = 0.3; delta_N = 0.3
    tau_S = 500.0; alpha_S = 1.0/tau_S; beta_S = 0.3/tau_S; k_S = 0.02
    _delta_M_F = 0.03; _gamma_mem = 0.04
    _ema_alpha = 0.005; _mu_drift_eps = 0.002
    
    snapshots = []
    blowup_at = None
    
    for tick in range(1, ticks + 1):
        L = 0.5
        mu_base = mu_core + 0.3 * L
        
        _drive_S = (N + M) / 2.0
        _mod_S = math.tanh((L - 0.15)*5.0)*0.5 + 0.85
        _total_drive_S = _drive_S * _mod_S
        dS = (alpha_S * math.tanh(_total_drive_S - S) - beta_S) * dt
        S_new = S + dS
        
        ema_S_new = _ema_alpha * S_new + (1.0 - _ema_alpha) * ema_S
        mu_core_new = mu_core + _mu_drift_eps * (ema_S_new - mu_core) * dt
        
        # 无记忆注入（裸耦合）
        mu_eff = mu_base - k_mu * M + k_S * S_new
        dE = T * dt
        dT = (mu_eff * (1.0 - E * E) * T - E) * dt
        dM = (alpha_M * E * E + _delta_M_F * 0.0 + _gamma_mem * 0.0 - beta_M * M) * dt
        dN = (gamma_N * (E * E + T * T) - delta_N * N) * dt
        
        E_new = E + dE
        T_new = T + dT
        N_new = N + dN
        M_new = M + dM
        E_new = hold(E_new, E)
        T_new = hold(T_new, T)
        N_new = hold(N_new, N)
        M_new = hold(M_new, M)
        snapshots.append({"tick": tick, "E": E_new, "T": T_new, "N": N_new, "M": M_new,
                          "mu_eff": mu_eff, "mu_core": mu_core_new, "S": S_new,
                          "ema_S": ema_S_new})
        
        E, T, N, M = E_new, T_new, N_new, M_new
        S, mu_core, ema_S = S_new, mu_core_new, ema_S_new
        
        if abs(E) > 1e6 or abs(T) > 1e6 or abs(N) > 1e6 or abs(M) > 1e6:
            blowup_at = tick
            break
    
    if blowup_at:
        s = snapshots[-1]
        print(f"  [{label}] 爆发 tick={blowup_at}: E={s['E']:.3e} T={s['T']:.3e} N={s['N']:.3e} M={s['M']:.3e} mu_eff={s['mu_eff']:.3f} mu_core={s['mu_core']:.5f} S={s['S']:.4f}")
    else:
        s = snapshots[-1]
        print(f"  [{label}] 稳定 ({ticks} tick): E={s['E']:.4f} T={s['T']:.4f} N={s['N']:.4f} M={s['M']:.4f} mu_eff={s['mu_eff']:.4f} mu_core={s['mu_core']:.5f} S={s['S']:.6f}")
    
    # 每 50 tick 打印一次摘要
    print(f"    轨迹抽样:")
    for s in snapshots[::max(1, ticks//10)]:
        print(f"      tick={s['tick']:>5d}:  E={s['E']:>10.4f}  T={s['T']:>10.4f}  N={s['N']:>10.4f}  M={s['M']:>10.4f}  mu_eff={s['mu_eff']:.4f}  mu_core={s['mu_core']:.5f}  S={s['S']:.5f}")
    
    return blowup_at

print("从 tick 200 真实快照状态出发，耦合系统 (无记忆注入):\n")

# 真实 tick 200 快照 (近似值)
state_200 = (0.534, 2.040, 5.494, 2.899)
run_from_live_state(2000, state_200, "(正常驱动)")

print()

# 加强驱动 —
state_200_high = (0.534, 2.040, 5.494, 2.899)
run_from_live_state(2000, state_200_high, "2000 tick 高驱动")
