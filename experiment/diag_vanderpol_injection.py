#!/usr/bin/env python3
"""
诊断 (b)：逐步注入各因素，定位哪一个打破 van der Pol 极限环
每一步在前一步基础上加一项，追踪变量何时开始失控
"""
import math

def hold(new, prev):
    if math.isnan(new) or math.isinf(new):
        return prev
    return new

def run(config, n_ticks=200, label=""):
    E, T, N, M = 0.5, 0.3, 0.5, 0.3
    S, mu_core, ema_S = 0.0, 0.5, 0.0

    dt = 0.08
    k_mu = 0.1; alpha_M = 0.8; beta_M = 0.8; gamma_N = 0.3; delta_N = 0.3
    tau_S = 500.0; alpha_S = 1.0/tau_S; beta_S = 0.3/tau_S; k_S = 0.02
    _delta_M_F = 0.03; _gamma_mem = 0.04
    _ema_alpha = 0.005; _mu_drift_eps = 0.002

    snapshots = []
    blowup_tick = None

    for tick in range(1, n_ticks + 1):
        L = 0.5
        mu_base = mu_core + 0.3 * L

        _drive_S = (N + M) / 2.0
        _mod_S = math.tanh((L - 0.15)*5.0)*0.5 + 0.85
        _total_drive_S = _drive_S * _mod_S + (0.02 * config.get("F", 0.0))
        dS = (alpha_S * math.tanh(_total_drive_S - S) - beta_S) * dt
        S_new = S + dS
        ema_S_new = _ema_alpha * S_new + (1.0 - _ema_alpha) * ema_S
        mu_core_new = mu_core + _mu_drift_eps * (ema_S_new - mu_core) * dt

        # 注入项
        _dE_mem = config.get("dE_mem", 0.0)
        _dT_mem = config.get("dT_mem", 0.0)
        _dN_mem = config.get("dN_mem", 0.0)
        _total_act = config.get("total_act", 0.0)

        E_i = E + config.get("r_e_off", 0.0) * 0.1
        T_i = T + config.get("r_t_off", 0.0) * 0.1
        N_i = N + config.get("r_n_off", 0.0) * 0.1
        M_i = M

        mu_eff = mu_base - k_mu * M_i + k_S * S_new
        dE = T_i * dt + _dE_mem * dt
        dT = (mu_eff * (1.0 - E_i * E_i) * T_i - E_i) * dt + _dT_mem * dt
        dM = (alpha_M * E_i * E_i + _delta_M_F * config.get("F", 0.0) + _gamma_mem * _total_act - beta_M * M_i) * dt
        dN = (gamma_N * (E_i * E_i + T_i * T_i) - delta_N * N_i + _dN_mem) * dt

        E_new = hold(E_i + dE, E_i)
        T_new = hold(T_i + dT, T_i)
        N_new = hold(N_i + dN, N_i)
        M_new = hold(M_i + dM, M_i)

        snapshots.append({"tick": tick, "E": E_new, "T": T_new, "N": N_new, "M": M_new, "mu_eff": mu_eff})

        E, T, N, M = E_new, T_new, N_new, M_new
        S, mu_core, ema_S = S_new, mu_core_new, ema_S_new

        if abs(E) > 1e10 or abs(T) > 1e10 or abs(N) > 1e10 or abs(M) > 1e10:
            blowup_tick = tick
            break

    # 报告
    if blowup_tick:
        s = snapshots[-1]
        print(f"  [{label}] 爆发 tick={blowup_tick}:  E={s['E']:.3e}  T={s['T']:.3e}  N={s['N']:.3e}  M={s['M']:.3e}  mu_eff={s['mu_eff']:.3f}")
    else:
        s = snapshots[-1]
        print(f"  [{label}] 稳定 ({n_ticks} tick):  E={s['E']:.3f}  T={s['T']:.3f}  N={s['N']:.3f}  M={s['M']:.3f}  mu_eff={s['mu_eff']:.3f}")
    return blowup_tick

print("逐步注入测试:\n")

# 0. 裸 van der Pol（已在上一轮确认稳定）
run({}, 300, "裸 van der Pol")

# 1. 加入 N 持续注入（模拟记忆持续回流 dN_mem）
run({"dN_mem": 0.5}, 300, "dN_mem=0.5 (持续N回流)")

# 2. 加强度
run({"dN_mem": 2.0}, 300, "dN_mem=2.0")

# 3. E 持续注入
run({"dE_mem": 0.5}, 300, "dE_mem=0.5")

# 4. T 持续注入
run({"dT_mem": 0.5}, 300, "dT_mem=0.5")

# 5. 组合：E+N+T 全注入
run({"dE_mem": 0.2, "dT_mem": 0.2, "dN_mem": 0.5}, 300, "组合注入")

# 6. M 通过 total_act 驱动
run({"total_act": 1.0}, 300, "total_act=1.0")

# 7. 强记忆引力（模拟情景记忆持续激活）
run({"dE_mem": 0.3, "dT_mem": 0.3, "dN_mem": 1.0, "total_act": 0.5}, 300, "强记忆引力")

# 8. 长时间 (1000 tick) 裸跑
print()
run({}, 1000, "裸 van der Pol (1000 tick)")
run({"dE_mem": 0.1, "dT_mem": 0.1, "dN_mem": 0.2, "total_act": 0.1}, 1000, "弱注入 (1000 tick)")
