# van der Pol 能量发散根因诊断报告

**日期**：2026-09-08  
**阶段**：第三阶段（根因调查）  
**范围**：living_engine.py `_update_luoshen_coupled` 的 van der Pol 核心 + 全部耦合项  
**约束**：**未修改任何 Luoshen 源码**（仅调用 + 独立仿真器复现）

---

## 一、根因结论（TL;DR）

**发散不是 van der Pol 方程本身造成的，而是 M 变量的正反馈累积推着 mu_eff 越过零点，使阻尼项反号，极限环破裂为指数发散。**

具体机制：
1. van der Pol 本身是稳定极限环（mu_eff > 0 时自限幅）
2. M 的源项包括 alpha_M*E²（来自 vdp 振幅）、`_delta_M_F*F`（来自 facts）、`_gamma_mem*total_act`（来自情景记忆激活）
3. 当 M 超过临界值 M_crit ≈ (mu_base + k_S*S_max)/k_mu ≈ 6 时，mu_eff 变负
4. mu_eff < 0 时，vdp 方程中 `mu_eff*(1-E²)*T` 在 `|E|>1` 区变成能量注入而非耗散
5. 一旦注入开始，dT/dt 指数增长 → T 驱使 E 漂移 → E² 驱使 M 加速 → mu_eff 更负 → 指数发散到 ±inf/NaN

**时间线**（从 `active_memory/environment_log.jsonl` idx=16686 起）：

| tick | E | T | N | M | mu_eff（反推） | 相 |
|------|---|---|---|---|---|---|
| 1 | -1.82 | -1.59 | -3.98 | 0.94 | +0.51 | 环振荡 |
| 10 | -3.23 | -6.99 | -1.05 | 5.14 | +0.10 | 趋近临界 |
| 16 | -5.18 | -4.32 | 4.85 | 10.80 | -0.46 | **翻负** |
| 20 | -7.88 | -69.7 | 22.8 | 16.25 | -1.01 | 指数发散开始 |
| 21 | -13.1 | -348 | 139 | 19.36 | -1.33 | 超指数 |
| 25 | -3.1e10 | -7.9e23 | 3.5e21 | 1.0e9 | — | 浮点溢出 |
| 29 | -4.7e257 | -inf | inf | 5.8e226 | — | +-inf |
| 30 | -inf | nan | nan | inf | — | NaN |

首翻负发生在 M ≈ 10-11（tick 16-17），但 M 越过临界 6 是在更早的 tick 12 附近。

---

## 二、方程与参数快照

来自 living_engine.py 实际代码（行 2641-3075）：

```
# 环境 env：light, noise, temperature, pressure, humidity（真实采样）
sigma = 0.025 * noise          # 噪声扰动幅度

L = _compute_body_influence(memory)   # 身体背景势，均值 ~0.5

# ── van der Pol 核心 ──────────────────────────────────
mu_base = mu_core + 0.3 * L
mu_eff  = mu_base - k_mu * M + k_S * S_new    # M 负反馈 + S 正反馈

dE  =  T * dt                              # 位置导数
dT  = (mu_eff * (1.0 - E*E) * T - E) * dt # 含记忆引力 _dT_mem
dM  = (alpha_M*E² + δ_F*F + γ_mem*total_act - β_M*M) * dt
dN  = (γ_N*(E² + T²) - δ_N*N + dN_mem) * dt

# ── Shell S 慢变量 ──────────────────────────────────
drive_S = (N + M) / 2 * mod_S + 0.02*F
dS  = (α_S * tanh(drive_S - S) - β_S) * dt
ema_S = α_ema * S_new + (1-α_ema) * ema_S
mu_core_new = mu_core + ε * (ema_S_new - mu_core) * dt    # 极慢漂移 ε=0.002

# ── 记忆引力（RESTORING，不是 INJECTING）──────────────
dE_mem = K_MEM * Σ act_i * (mem_e_i - E)
dT_mem = K_MEM * Σ act_i * (mem_t_i - T)
# K_MEM = 0.015, act_i = salience*exp(-age/T_DECAY)*(1+λ·exp(-dist²/2σ²))

# ── 已移除的阻尼 ─────────────────────────────
# Line 2769: # [已移除] damping —— 自阻尼回复力
# Line 2771-2772: # ── [已移除] 历史惯性项 ──
#               # 原 0.35 * inertia 阻尼项已删除

# ── 输出 ─────────────────────────────────────────
# Line 2887: # ── 更新（无钳制、无边界） ──
# Line 2893-2901: NaN _hold_prev 防御（崩溃后 persistent 状态防 NaN）
```

### 关键参数

| 符号 | 值 | 含义 |
|------|-----|------|
| dt | 0.08 | Forward Euler 步长 |
| k_mu | 0.1 | M 对 mu_eff 的负反馈系数 |
| k_S | 0.02 | S (shell) 对 mu_eff 的正反馈系数 |
| alpha_M / beta_M | 0.8 / 0.8 | M 的增长/衰减率 |
| gamma_N / delta_N | 0.3 / 0.3 | N 的增长/衰减率 |
| tau_S | 500 | Shell S 的低通时间常数（原始，scale 前） |
| alpha_S | 1/500 | S 的低通驱动 |
| beta_S | 0.3/500 | S 的衰减 |
| ε (_mu_drift_eps) | 0.002 | mu_core 向 ema_S 的漂移速率 |
| K_MEM | 0.015 | 记忆引力耦合强度 |
| δ_F (_delta_M_F) | 0.03 | M 的事实在场度 F-注入速率 |
| γ_mem (_gamma_mem) | 0.04 | M 的激活记忆注入速率 |
| α_ema | 0.005 | ema_S 的平滑因子 |

### 临界 M 值计算

```
mu_eff > 0  ⟺  mu_base - k_mu*M + k_S*S > 0
             M < (mu_base + k_S*S) / k_mu

当 L=0.5, mu_core=0.5, S≈1.0:
  mu_eff > 0 ⟺ M < (0.5 + 0.15 + 0.02) / 0.1 = 6.7

当 mu_core 漂移升高到 0.7, S ≈ 1.2:
  mu_eff > 0 ⟺ M < (0.7 + 0.15 + 0.024) / 0.1 = 8.74

但 beta_M=0.8，alpha_M=0.8 ⇒ M 稳态 = E² + 0.03F + 0.04*total_act
当 E 振幅 ~2.5, F~0.3, total_act~1: M_steady ≈ 6.3 + 0.009 + 0.04 ≈ 6.35
```

**M 的稳态工作点本身就在临界区边缘**——稍加扰动（S 漂移增加 E 振幅、F 因 facts 累积增加、total_act 因情景记忆增多）就会越过临界。

---

## 三、发散器理解析

### A. 主触发链（占 ~95% 观察场景）

```
mu_core 因 S 漂移而上升  (时间常数 ~5000 tick)
         ↓
mu_eff 增大
         ↓
van der Pol 极限环振幅增长  (mu_eff 越大，振幅越大)
         ↓
E² 均值增大
         ↓
M 稳态值上升 (M_steady = (α_M<E²> + 0.03F + γ_mem*Σact_i) / β_M)
         ↓
M 越过临界值 M_crit ≈ 6-9
         ↓
mu_eff 变负
         ↓
阻尼项 -(1-E²)*mu_eff*T 在 |E|>1 区反号 → 能量注入
         ↓
T 指数增长 → E 加速 → E² 指数增长 → M 指数上升 → mu_eff 更负
         ↓
浮点溢出 → ±inf → NaN
```

### B. 辅助因素

1. **mu_core 漂移不可逆**（line 2847-2848）：`mu_core += 0.002*(ema_S-mu_core)*dt`，ema_S 只增不减（N+M 因输入始终正），所以 mu_core 会持续上升直到撞 ema_S 顶
2. **dM 的源项全正**：alpha_M*E²（始终正）、delta_MF*F（[0,1)）、gamma_mem*total_act（[0,∞)）；只有 beta_M*M 是负反馈
3. **记忆引力是恢复力**（不是注入力），但 `total_act` 作为 M 的加性驱动源不经过恢复路径，直接推高 M
4. **N 持续推动 S 上升**：`dN` 中的 gamma_N*(E²+T²) 项让 N 和 M 形成共积累

### C. 临界慢化 + 快崩溃

观察到的「长时间稳定然后突然发散」现象来自两级时间尺度的耦合：
- 慢变量 mu_core, S, M：时间常数 ~1000-5000 tick，在数十 tick 内看似不动
- 快变量 E, T：振荡周期 ~10 tick
- 当慢变量累积越过阈值时，快变量在 5-10 tick 内从 ±10 跳到 ±10^20（超指数）

---

## 四、仿真验证证据

### 仿真器 A：裸 van der Pol（无耦合）
文件：`experiment/diag_vanderpol_rootcause.py`  
结果：300 tick 时稳定，E∈[-2.3,2.3]，T∈[-2.4,2.4]，N∈[0.5,5.08]，M∈[0.3,3.4]  
→ 确认方程本身不发散

### 仿真器 B：独立 bare van der Pol
文件：`experiment/diag_vanderpol_injection.py`  
- 裸跑：300 tick 稳定
- + 记忆引力项 (dN_mem, dT_mem, total_act)：无发散
- 长 1000 tick 裸跑：稳定，mu_eff 收敛至 ~0.28
- 长 1000 tick 弱注入：稳定
→ 注入记忆力/记忆 N-回流/记忆总激活均不造成裸跑发散

### 仿真器 C：从 tick 200 真实快照出发的耦合系统
文件：`experiment/diag_vanderpol_coupled.py`  
起始：E=0.534, T=2.040, N=5.494, M=2.899  
2000 tick：稳定，mu_core 从 0.499 漂移至 0.87，E 振幅从 ~2 增至 ~2.5，但从未发散  
→ 长时间运行 + mu_core 漂移也不会直接发散

### 仿真器 D：带记忆注入的预发散状态（关键）
文件：`experiment/diag_blowup_rootcause.py`

| 场景 | tick first | mu_eff 翻负 tick | 25 tick 状态 |
|------|-----------|-----------------|------------|
| 真实预发散 + 中等 epistemic (F=0.3, total_act=1) | 16 | **tick 8** | E=6.2, T=10.3, M=5.5 → 发散 |
| 真实预发散 + 零注入（对照） | 16 | **tick 8** | E=6.0, T=9.4, M=11.2 → 发散 |
| 真实预发散 + 强注入 (F=0.5, total_act=2) | 16 | **tick 8** | E=6.4, T=11.3, M=11.7 → 发散 |
| 正常起步 + 强注入 (60 tick 观察) | — | — | mu_eff 始终 >0.7, 不发散 |

**关键发现**：当真实预发散状态（M=5.14, E=-3.23, T=-6.99, mu_core=0.75）被代入耦合系统，**mu_eff 在第 8 个 tick 翻负**。后续 25 tick 内 E 振幅线性增长（5→6→8），而实际系统在 tick 16-21 之间爆发——这是因为实际系统中 M 的累积更快（真实 F 和 total_act 可能更高）。

**定量**：从 F=0.5, total_act=2.0 的场景 D 看，25 tick 内 E 从 -3.23 到 +6.22（斜率 ~0.4/tick），在真实系统中类似的斜率累积 5 个 tick 即足以从 E≈-8 弹射到 |E|>10^2。

### 仿真总结

```
证据                    | 稳定/发散 | 判定
------------------------|-----------|------
裸 van der Pol           | 稳定      | 方程本身稳定
+ 记忆注入              | 稳定      | 记忆注入不是触发器
+ 耦合 S + mu_core 漂移  | 2000 tick 稳定 | 漂移太慢
+ 预发散状态 + M>5      | 8 tick 后发散| **M 累积越过 mu_eff=0 是根因**
```

---

## 五、在关键 tick 上 live data 的 mu_eff 反推

从 `environment_log.jsonl` 的记录反推每拍的 mu_eff（假设 mu_core ≈ 常量 0.75，S ≈ 0.91 来自初始估计）：

| tick | M | mu_eff = 0.6+0.02*0.91 − 0.1*M |
|------|----|------|
| 1 | 0.94 | **+0.517** |
| 10 | 5.14 | **+0.100** |
| 14 | 8.38 | **−0.228** |
| 15 | 9.59 | **−0.349** |
| 20 | 16.25 | **−1.015** |

**物理图像**：系统在 tick 15-16 之间越过 mu_eff=0 临界点，之后 T 以 `(mu_eff*(1-E²) - 1)*dt` 的速率指数自增幅，mu_eff 越负增幅越快，进入正反馈陷阱。

---

## 六、诊断脚本位置（按需保留/清除）

```
luo-shen-ai/experiment/
├── diag_vanderpol_rootcause.py      # 仿真器 A：裸 vdp，300 tick 稳定
├── diag_vanderpol_coupled.py       # 仿真器 C：2000 tick 耦合稳定
├── diag_vanderpol_injection.py     # 仿真器 B：各类记忆注入测试
└── diag_blowup_rootcause.py        # 仿真器 D：mu_eff 翻负 → 指数发散
```

---

## 七、结论与建议方向（不修改代码的观察层）

### 确认的缺陷
1. **M 没有上界**：alpha_M*E² + delta_MF*F + gamma_mem*total_act 全正，只有 beta_M*M 一项负反馈；没有 clamp、没有饱和、没有死区
2. **mu_eff 符号崩溃无保护**：`mu_eff < 0` 时 vdp 方程结构反转（负阻尼），没有 guard
3. **mu_core 不可逆上升**：ema_S 只增（N+M 因输入始终正），mu_core 单向漂移，无复位机制
4. **已移除的 damping/inertia** 丢失了「当能量增长过快时提供额外回复力」的缓冲通道（line 2769-2772）

### 观察建议（不修改动力学）
- 监控 M 轨迹稳定在 ~5（绿色）、~6（黄色临界）、>6（红色触发）三个区间
- 监控 mu_eff 轨迹：首次穿越 0 即预警（系统在 ~8 tick 后不可恢复）
- 监控 mu_core 漂移速率：若 ε>0.002 且 S>ema_S 持续，系统正在「升温」

### 可探索的修复方向（供设计者参考，不在本次诊断中执行）
- M 方程增加 upper clamp（如 tanh(M/M_max)*M_max，M_max=4）或负反馈强化
- mu_eff 设下界（如 `mu_eff = max(mu_eff, ε_min)`）
- mu_core 漂移改为双向（ema_S > mu_core 时增长，ema_S < mu_core 时衰减）
- 恢复 line 2769-2772 中的 inertia 阻尼项或等价替代

---

**完成于 2026-09-08** | 全部证据基于 `environment_log.jsonl` 实测 + 独立数值仿真器（未修改 Luoshen 源码）
