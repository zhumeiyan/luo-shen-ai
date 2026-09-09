#!/usr/bin/env python3
"""
诊断 (d)：验证根因链

假说：记忆激活与 F 注入导致 M 上冲 → mu_eff 翻负 → van der Pol 阻尼反号 → 指数发散

关键方程：mu_eff = mu_base + 0.3*L - k_mu*M + k_S*S_new
  当 k_mu*M > mu_base + 0.3*L → mu_eff < 0 → (1-E²)*mu_eff*T 项反号
  → |E|>1 区域变成能量注入 → 加速 → 再注入 → 指数级发散
"""
import math

def run_pre_blowup_sim(initial_state, k_ic=0.3, F_val=0.3, total_act_val=1.0, n_ticks=25):
    E, T, N, M = initial_state
    S = max(0.0, (N + M) / 4.5)
    mu_core = 0.75  # 从 prior run 漂移后的假设值
    ema_S = 0.70
    
    dt = 0.08
    k_mu = 0.1; alpha_M = 0.8; beta_M = 0.8
    gamma_N = 0.3; delta_N = 0.3
    tau_S = 500.0; alpha_S = 1.0/tau_S; beta_S = 0.3/tau_S; k_S = 0.02
    _delta_M_F = 0.03; _gamma_mem = 0.04
    _ema_alpha = 0.005; _mu_drift_eps = 0.002
    
    print(f'初始状态: E={E:.3f}, T={T:.3f}, N={N:.3f}, M={M:.3f}')
    print(f'注入: F={F_val}, total_act={total_act_val}')
    print(f'假设: mu_core={mu_core}, k_ic={k_ic}')
    print()
    
    blowup_at = None
    mu_eff_flip = None
    
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
        
        # 记忆注入项：dN_mem 来自 gravity
        dN_mem = k_ic * total_act_val * (0.0 - N)  # 吸引力微弱（N 接近 0）
        _total_act = total_act_val
        
        mu_eff = mu_base - k_mu * M + k_S * S_new
        if mu_eff_flip is None and mu_eff < 0:
            mu_eff_flip = tick
        
        dE = T * dt
        dT = (mu_eff * (1.0 - E * E) * T - E) * dt
        dM = (alpha_M * E * E + _delta_M_F * F_val + _gamma_mem * total_act_val - beta_M * M) * dt
        dN = (gamma_N * (E * E + T * T) - delta_N * N + dN_mem) * dt
        
        E_new = E + dE
        T_new = T + dT
        N_new = N + dN
        M_new = M + dM
        
        print(f'  tick={tick:>2d}: E={E_new:>12.4f}  T={T_new:>12.4f}  N={N_new:>10.4f}  M={M_new:>10.4f}  mu_eff={mu_eff:>8.4f}  mu_core={mu_core:>6.4f}  S={S_new:>8.5f}')
        
        if abs(T_new) > 1e6 or abs(E_new) > 1e6 or abs(M_new) > 1e6:
            blowup_at = tick
            print(f'  → EXCEEDS 1e6 at tick {tick}')
            break
        
        E, T, N, M = E_new, T_new, N_new, M_new
        S, mu_core, ema_S = S_new, mu_core_new, ema_S_new
    
    return blowup_at, mu_eff_flip

# 真实发散的起点状态 (env_log idx=16686 pre-reset state was E=-3.23, T=-6.99, N=-1.05, M=5.14)
print("=== 场景 1: 真实预发散状态 + 中等记忆激活 ===")
run_pre_blowup_sim((-3.23, -6.99, -1.05, 5.14), F_val=0.3, total_act_val=1.0)

print()
print("=== 场景 2: 预发散状态 + 零记忆注入（对照） ===")
run_pre_blowup_sim((-3.23, -6.99, -1.05, 5.14), F_val=0.0, total_act_val=0.0)

print()
print("=== 场景 3: 预发散状态 + 强记忆激活 ===")
run_pre_blowup_sim((-3.23, -6.99, -1.05, 5.14), F_val=0.5, total_act_val=2.0)

print()
print("=== 场景 4: 正常起步 + 强记忆注入（验证是否从头就发散）===")
run_pre_blowup_sim((0.5, 0.3, 0.5, 0.3), F_val=0.5, total_act_val=2.0, n_ticks=60)
