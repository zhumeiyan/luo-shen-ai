#!/usr/bin/env python3
"""
诊断：van der Pol 能量发散根因（独立脚本，不修改洛神）
复现 _update_luoshen_coupled 的 van der Pol 环形核心 + 辅助变量演化
追踪每个变量的增长速率，定位哪个项导致无界增长
"""
import math

# ====== 洛神 van der Pol 核心方程（完整复制，无修改） ======
# 来源：living_engine.py 第 2869-2901 行 + 辅助变量方程

def run_simulation(n_ticks=300, verbose=True):
    # 初始条件（来自洛神冷启动）
    E = 0.5
    T = 0.3
    N = 0.5
    M = 0.3

    # 辅助变量初始
    S = 0.0
    mu_core = 0.5
    ema_S = 0.0

    # 参数（来自洛神源码）
    dt = 0.08
    k_mu = 0.1
    alpha_M = 0.8
    beta_M = 0.8
    gamma_N = 0.3
    delta_N = 0.3
    tau_S = 500.0
    alpha_S = 1.0 / tau_S
    beta_S = 0.3 / tau_S
    k_S = 0.02
    _delta_M_F = 0.03
    _gamma_mem = 0.04
    _ema_alpha = 0.005
    _mu_drift_eps = 0.002

    # 记忆引力 / 残差 / F — 设为 0 以观察裸 van der Pol 是否本身稳定
    _dE_mem = 0.0
    _dT_mem = 0.0
    _dN_mem = 0.0
    _total_act = 0.0
    _F = 0.0
    _r_e_off = 0.0
    _r_t_off = 0.0
    _r_n_off = 0.0
    L = 0.5

    # 噪声
    sigma = 0.0

    history = []

    for tick in range(1, n_ticks + 1):
        # mu_base
        mu_base = mu_core + 0.3 * L

        # 壳 S
        _drive_S = (N + M) / 2.0
        _mod_S = math.tanh((L - 0.15) * 5.0) * 0.5 + 0.85
        _total_drive_S = _drive_S * _mod_S + 0.02 * _F
        dS = (alpha_S * math.tanh(_total_drive_S - S) - beta_S) * dt
        S_new = S + dS

        # ema_S / mu_core 漂移
        ema_S_new = _ema_alpha * S_new + (1.0 - _ema_alpha) * ema_S
        mu_core_new = mu_core + _mu_drift_eps * (ema_S_new - mu_core) * dt

        # 残差注入（= 0）
        E_i = E + _r_e_off * 0.1
        T_i = T + _r_t_off * 0.1
        N_i = N + _r_n_off * 0.1
        M_i = M

        # van der Pol 核心
        mu_eff = mu_base - k_mu * M_i + k_S * S_new
        dE = T_i * dt + _dE_mem * dt
        dT = (mu_eff * (1.0 - E_i * E_i) * T_i - E_i) * dt + _dT_mem * dt

        # M / N
        dM = (alpha_M * E_i * E_i + _delta_M_F * _F + _gamma_mem * _total_act - beta_M * M_i) * dt
        dN = (gamma_N * (E_i * E_i + T_i * T_i) - delta_N * N_i + _dN_mem) * dt

        # 无钳制更新
        E_new = E_i + dE
        T_new = T_i + dT
        N_new = N_i + dN
        M_new = M_i + dM

        # NaN/Inf 防御
        def hold(new, prev):
            if math.isnan(new) or math.isinf(new):
                return prev
            return new
        E_new = hold(E_new, E_i)
        T_new = hold(T_new, T_i)
        N_new = hold(N_new, N_i)
        M_new = hold(M_new, M_i)

        # 采样记录
        history.append({
            "tick": tick,
            "E": E_new, "T": T_new, "N": N_new, "M": M_new,
            "mu_eff": mu_eff,
            "mu_core": mu_core_new,
            "S": S_new,
            "dE": dE, "dT": dT, "dN": dN, "dM": dM,
            "ema_S": ema_S_new,
        })

        # 推进
        E, T, N, M = E_new, T_new, N_new, M_new
        S = S_new
        mu_core = mu_core_new
        ema_S = ema_S_new

        # 爆发检测：E 超过 1e10 时报告并中断
        if abs(E) > 1e10 or abs(T) > 1e10 or abs(N) > 1e10 or abs(M) > 1e10:
            print(f"\n!!! BLOWUP at tick {tick}: E={E:.3e}, T={T:.3e}, N={N:.3e}, M={M:.3e}")
            # 再跑几步追踪
            return history, tick

        if verbose and tick % 50 == 0:
            print(f"tick {tick:>4d}: E={E:>12.4f}  T={T:>12.4f}  N={N:>12.4f}  M={M:>12.4f}  "
                  f"mu_eff={mu_eff:.4f}  mu_core={mu_core:.5f}")

    return history, n_ticks


# ====== 运行模拟（无外部裸 van der Pol） ======
hist, last_tick = run_simulation(300)

print("\n" + "="*70)
print("裸 van der Pol 测试结论（无记忆引力、无残差扰动）")
print("="*70)
if last_tick < 300:
    print(f"结果：变量于 tick {last_tick} 溢出")
else:
    final = hist[-1]
    print(f"结果：300 tick 后稳定")
    print(f"  E={final['E']:.6f}, T={final['T']:.6f}, N={final['N']:.6f}, M={final['M']:.6f}")
    print(f"  mu_eff={final['mu_eff']:.5f}, mu_core={final['mu_core']:.6f}")

# ====== 附加测试：追踪增长率 ======
print("\n变量增长速率追踪（每 50 tick 采样）")
print(f"{'tick':>6s}  {'|E|':>12s}  {'|T|':>12s}  {'|N|':>12s}  {'|M|':>12s}  {'mu_eff':>8s}")
for i in range(0, len(hist), 50):
    h = hist[i]
    print(f"{h['tick']:>6d}  {abs(h['E']):>12.4f}  {abs(h['T']):>12.4f}  "
          f"{abs(h['N']):>12.4f}  {abs(h['M']):>12.4f}  {h['mu_eff']:>8.4f}")

# ====== 追踪哪个变量最先突破阈值 ======
print("\n各变量突破阈值时间")
thresholds = [1.0, 10.0, 100.0, 1e6, 1e50]
for var in ['E', 'T', 'N', 'M']:
    print(f"  {var}:")
    for thr in thresholds:
        hit = None
        for h in hist:
            if abs(h[var]) > thr:
                hit = h['tick']
                break
        status = f"tick {hit:>4d}" if hit else "未突破"
        print(f"    |{var}| > {thr:.0e}: {status}")
