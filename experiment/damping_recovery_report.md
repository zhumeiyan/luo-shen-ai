# 被移除阻尼项定位与恢复评估

**日期**: 2026-09-08  
**阶段**: 第三阶段 — 根因定位 + 修复候选评估  
**约束**: 未修改 living_engine.py；所有实验在独立仿真器运行  

---

## 一、定位结果

### 找到的原始代码片段

**来源**: commit `8d488a7` / `a02ffc7` / `60b7fd1` 中的 `_evolve_climate_idle`（静息更新），至今仍在当前代码 line 1395-1475。该函数在每次 `idle_update_memory`（沉默路径）时调用。

```python
# lines 1427-1463 of living_engine.py (当前版本)
c_EN = 0.14
damping = 0.15

# 二阶差分（历史惯性 = 机械系统中的加速度项）
E_inertia = hE[-1] - 2*hE[-2] + hE[-3]
T_inertia = hT[-1] - 2*hT[-2] + hT[-3]
N_inertia = hN[-1] - 2*hN[-2] + hN[-3]
M_inertia = hM[-1] - 2*hM[-2] + hM[-3]

dE = (0.12*T - c_EN*N + 0.05*M
      - damping * E           # 自阻尼
      - 0.35 * E_inertia      # 历史惯性阻尼
      ) * step_factor

dT = (0.10*E + 0.06*M - c_EN*N
      - damping * T
      - 0.35 * T_inertia
      ) * step_factor

dN = (c_EN*E - 0.07*T - 0.10*N + 0.02
      - 0.35 * N_inertia
      ) * step_factor

dM = (0.09*T + 0.04*E - 0.14*M
      - 0.35 * M_inertia
      ) * step_factor

# 更新并钳制到 [0, 1]
E_new = max(0.0, min(1.0, E + dE))
T_new = max(0.0, min(1.0, T + dT))
N_new = max(0.0, min(1.0, N + dN))
M_new = max(0.0, min(1.0, M + dM))
```

### 结论：原来是否存在防止 M 无限累积的机制？

**早期存在（在 idle 版本中），但被 vdp 重写时废弃**。具体：

1. `damping=0.15` 自阻尼：对 E 和 T 有线性回复力，帮助把系统压在零附近，间接抑制 M 的累积来源 E²。
2. `0.35 * inertia` 惯性阻尼：二阶差分项在 E/T/N/M 中充当"机械减震器"，平滑突发跳动。
3. `[0,1]` clamp：**这是 M 的硬性上界**，原 idle 版本中 M 不可能超过 1。
4. **但以上三项仅在 `_evolve_climate_idle` 中存在**，不受 `environment_tick` 通道的 van der Pol 动力学保护。

`# [已移除]` 注释（line 2769, 2771-2772）是设计者把 idle 的阻尼项移植到 vdp 主环时留下的"幽灵注释"——**vdp 主环从未真正地部署过等价的阻尼项**。代替它的是 `mu_eff = mu_base - k_mu*M + k_S*S`：用 M 的反馈位置代替，但**这个反馈在 M>临界值时反而翻号变成正反馈**（已证）。

---

## 二、仿真结果数据

所有实验起始状态 = live blowup 前 tick 10: `E=-3.2339, T=-6.9900, N=-1.0489, M=5.1412`

### 主验证（起始预发散态，4 种 F/记忆激活组合）

| 变体 | F=0.1/act=0.5 | F=0.3/act=1.0 | F=0.5/act=2.0 | F=0.7/act=2.0 | M_max | mu_min |
|------|---------------|---------------|---------------|---------------|-------|--------|
| A 基线 vdp | **B@31** | **B@31** | **B@30** | **B@30** | 190-3800 | −2.2 ~ −7.0 |
| B idle 惯性 0.35 单移植 | **B@31** | **B@31** | **B@30** | **B@30** | 126-5940 | −2.2 ~ −8.2 |
| C idle 移植（阻尼 0.15+惯性 0.35） | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 10.8 | −0.17 |
| D2 logistic M-sat (M_max=6) | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 12.3 | **+0.33** |
| E2 EMC 软阻尼 (k=1,k2=0.5,M0=5) | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 10.7 | −0.15 |
| E3 EMC 软阻尼 (k=2,k2=0.6,M0=5) | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 9.4 | −0.02 |

### 冷启动验证（E=0.5/T=0.3/N=0.5/M=0.3，M 未达临界前）

| 变体 | F=0.1/act=0.5 | F=0.3/act=1.0 | F=0.5/act=2.0 | F=0.7/act=2.0 | M_max | mu_min |
|------|---------------|---------------|---------------|---------------|-------|--------|
| A 基线 | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 3.3 | 0.45 |
| C idle 移植 | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 2.0 | 0.60 |
| D2 logistic | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 3.3 | 0.51 |
| E2 soft | ✅ OK | ✅ OK | ✅ OK | ✅ OK | 3.0 | 0.48 |

冷启动下所有变体均稳定，证明修复只在 M 累积越过临界时起作用（不破坏正常行为）。

### 轨迹对比（F=0.3/act=1.0 @ tick 200-2000）

**基线 A**（已爆发） — tick 31 达 N=1.4e46, M=6e19, mu→−∞

**变体 C（idle 移植）**
```
tick=200:  E=0.84, T=-1.14, N=2.52, M=1.83  mu=0.73
tick=600:  E=-1.74, T=-0.37, N=2.67, M=1.47  mu=0.79
tick=1000: E=-0.16, T=1.64, N=2.32, M=1.37  mu=0.80
tick=1400: E=1.59, T=-0.49, N=2.66, M=2.02  mu=0.76
tick=2000: E=1.77, T=-0.05, N=2.74, M=1.74  mu=0.82
```
→ 环振荡收敛到有限幅（E∈[-2,2], M∈[1,2]），mu 恒定正 0.7~0.9

**变体 D2（logistic M-sat）**
```
tick=200:  E=-2.13, T=0.45, N=4.86, M=2.80  mu=0.69
tick=600:  E=-0.25, T=-2.34, N=4.27, M=1.68  mu=0.75
tick=1000: E=1.73, T=-0.87, N=4.71, M=3.24  mu=0.68
tick=1400: E=1.39, T=2.38, N=4.59, M=1.37  mu=0.81
tick=2000: E=2.09, T=-0.52, N=4.78, M=2.89  mu=0.75
```
→ mu 恒正 0.68~0.81 (未翻负！); M 仍振荡但影响环的 M_eff 被 logistic 钳制

**变体 E2（EMC softplus）**
```
tick=200:  E=1.66, T=-0.95, N=5.41, M=2.96  mu=0.62
tick=600:  E=2.18, T=0.09, N=4.88, M=2.01  mu=0.75
tick=1000: E=0.17, T=2.31, N=4.32, M=1.45  mu=0.79
tick=1400: E=-1.53, T=1.00, N=4.71, M=2.87  mu=0.67
tick=2000: E=0.85, T=2.68, N=4.45, M=1.16  mu=0.87
```
→ mu 恒正；M 被 softplus 拉回

---

## 三、推荐的最小修复方案

### 方案 1: Logistic M-saturation（推荐首选）

只改 **M 输入 mu_eff 的方式**，不动 vdp 方程本身：

```python
# 替换: mu_eff = mu_base - k_mu * M + k_S * S_new
# 为:
_k_sat = 0.5
_M_max = 6.0
_M_eff = _M_max * (1.0 / (1.0 + math.exp(-_k_sat * (M - _M_max * 0.6))))
mu_eff = mu_base - k_mu * _M_eff + k_S * S_new
```

数学性质:
- 连续、单调、无 if-then、梯度处处非零
- M→∞ 时 `_M_eff → M_max`，等价于软上界
- `k_mu*_M_eff` 最大为 `k_mu*_M_max = 0.6`，而 `mu_base ≥ 0.65+0.02*S`，所以 mu_eff 恒正 (>0.05)
- 不影响 E/T 的 van der Pol 极限环（该改的只是环的参数，不是环的形状）

### 方案 2: EMC softplus 加性阻尼（备选）

在 M 方程中**加一项连续软阻尼**，不碰其他方程：

```python
# 在 dM 中追加:
_k_emc = 1.0; _k2_emc = 0.5; _M0_emc = 5.0
_emc_term = -_k_emc * math.log(1.0 + math.exp(_k2_emc * (M - _M0_emc))) * dt
dM = (alpha_M * E * E + _delta_M_F * _F + _gamma_mem * _total_act - beta_M * M) * dt + _emc_term
```

数学性质:
- softplus `log(1+exp(x))` 是 ReLU 的光滑版，连续、无 if-then
- 当 M >> _M0_emc 时，_emc_term ≈ −_k_emc*(M−_M0_emc)，提供线性回复力
- 当 M < _M0_emc 时，_emc_term ≈ 0，几乎不干预正常工作区间
- 唯一缺点: M 仍会持续向上飘移（被软拉回，但平衡点上移到 ~6-7 而非无穷）

### 方案 3: 移植 idle 阻尼 + 惯性（轻量移植，最贴近原设计哲学）

```python
# 在 dE/dT/dN 中加入 idle 的阻尼项 (vdp 里没有):
_damping_idle = 0.15
dE += (-_damping_idle * E - 0.35 * E_inertia) * dt
dT += (-_damping_idle * T - 0.35 * T_inertia) * dt
# 注意: 必须有 damping_idle * E/T，只移植惯性 0.35 不够(变体 B 证明)
```

数学性质:
- 三个方程同时有弱线性回复力 + 速度减震
- 等价于给 vdp 极限环加一个"引力中心"——环越大被拉回越强
- 值 0.15 已足够（测试到 2000 tick）

---

## 四、是否建议应用到洛神主体

**首选方案 1 (logistic M-sat)，理由**:

1. **改动最小**: 只改 1 行 (M→mu_eff 映射)，不碰 E/T/N 方程
2. **理论干净**: 保证 mu_eff > 0 的硬约束，根因层面直接防翻负
3. **不影响环的本质**: vdp 极限环的形状/周期/振幅都保存；只是参数 mu_eff 永不翻负
4. **连续无 if-then**: sigmoid 是解析函数，梯度平滑
5. **值与物理意义对齐**: M_max=6 就是原来 idle `[0,1]` clamp 被重标度到 vdp 的域

**应用建议**:
- 在 living_engine.py line 2870 把 `mu_eff = mu_base - k_mu * M + k_S * S_new` 替换为 logistic 版本
- 若要保留 M 的"记录"意义（观测 / 哈希链 / 疼痛计算）：保留原始 M 值在 climate 中（不替换），只在 mu_eff 计算中用 _M_eff
- 记得在 environment_log 中同时输出 M（原始）和 M_eff（饱和后），便于后续观察
- 仿真已通过 4 种 F/记忆激活组合 × 2000 tick，无爆发

---

## 五、交付文件

```
luo-shen-ai/experiment/
├── diag_damping_recovery.py            ← 第一轮：各候选对比
├── diag_damping_recovery_extended.py  ← 扩展验证（×4 条件）
└── vanderpol_divergence_rootcause_report.md ← 上一阶段根因报告（未改）
```

---

**完成于**: 2026-09-08  
**核心发现**: 在 `_evolve_climate_idle` 中存在 `damping=0.15 + 0.35*inertia` 两项阻尼 + `[0,1]` clamp；vdp 重写时这三项均未移植到主环。logistic M-saturation（只改 1 行 M→mu_eff 映射）即可在 2000 tick 仿真中锁死 mu_eff>0，阻止正反馈陷阱。
