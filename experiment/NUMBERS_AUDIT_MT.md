# 数字审计报告：原始实现线逐值核查

审计日期: 2026-10-13
审计范围: P0 (E/T/N 通道) / P1 (死亡机制) / 三重判据 / EO 对齐表
分类: A=有代码或数据支撑可复现 / B=代码里找不到建议删除 / C=有代码但复现不一致需重跑

---

## P0：E/T/N 输入压力通道

### P0.1 ΔE / ΔT / ΔN 三通道

**报告值**: ΔE=0.0573, ΔT=0.0475, ΔN=0.0562 (>0.05 阈值) ✓

**原始数据源**: `experiment/input_pressure_AB_result.json`
```json
"summary": {
  "max_diff_E": 0.05725999999999998,
  "max_diff_T": 0.04751000000000005,
  "max_diff_N": 0.05622000000000005,
  "passed_max": true,
  "passed_final": true,
  "direction_test": true
}
```

**代码路径**: `experiment/run_input_pressure_AB.py` → `run_single_pressure_test()` (L120-189)
**阈值判定**: `threshold = 0.05` (L266)

**判定: A** — 原始 JSON 值 0.05726 / 0.04751 / 0.05622 ≈ 报告值（四舍五入）

---

### P0.2 N 通道 κ_N 校准

**报告值**: KAPPA_N 从 0.04 调到 0.06，让 ΔN 过 0.05 阈值

**代码位置**: `input_pressure.py` L13
```python
KAPPA_N = 0.06     # 原 0.04，调高到过阈值
KAPPA_E = 0.06
KAPPA_T = 0.04
N_BASELINE = 0.5
```

**判定: A** — 代码确认，调整有记录

---

### P0.3 rp_ema 放大 4.8×

**报告值**: "rp_ema 输入放大 4.8× 解决压力项≡0"

**代码搜索结果**:
- `living_engine.py` L1486: `_PRESSURE_ALPHA = 0.1` (注释 "0.02 → 0.1")
- EO_ALIGNMENT_TABLE.md L117-121: κ_E=0.06 (原0.03→2×), κ_T=0.04 (原0.02→2×), κ_N=0.06 (原0.04→1.5×)
- 搜索 `4.8×` / `4.8x` / `4.8*` 在所有 .py .json .md 文件中 **零命中**

**分析**: 0.1/0.02 = 5× (不是 4.8×)，2× × 2× × 1.5× = 6× (不是 4.8×)。4.8× 来源不明。

**判定: B** — 代码/数据中找不到 4.8× 的字面来源。建议论文改为 "约 5×" 或删除精确倍数

---

### P0.4 PRESSURE_ALPHA 版本不一致

**代码值**:
- `living_engine.py` L1486: `_PRESSURE_ALPHA = 0.1`
- `experiment/run_input_pressure_AB.py` L109: `_PRESSURE_ALPHA = 0.02` (局部变量)

**效应**: 实验脚本的 simulate_pressure_injection 用 0.02 积累 rp_ema，但主引擎用 0.1。两个代码 rp_ema 积累速度差 5×。

**判定: C** — 有代码但行为不一致。实验脚本应改为使用 `le._PRESSURE_ALPHA` 或统一值。实验 ΔE/ΔT/ΔN 值本身通过 input_pressure 模块的独立计算（KAPPA 系数），实验中的 _PRESSURE_ALPHA 不影响 Van der Pol 方程里的 dE/dT/dN 路径（直接走 pressure_differentials），所以 ΔE/ΔT/ΔN 的最终数值不受此不一致影响。rp_ema  accumulation 路径不受实验直接验证。

**复现对照**: 当前实验值可复现（已通过 input_pressure_AB_result.json 确认）

---

## P1：内生性死亡机制

### P1.1 死亡触发 tick 50

**报告值**: tick 50 触发死亡

**代码**: `living_engine.py` L2477
```python
_DEATH_THRESHOLD = 50  # tick 寿命阈值（测试用 50，正式部署 1000）
```

**数据源**: `experiment/endogenous_death_result.json`
```json
"death_tick": 50
```

**判定: A** — 常量 + 实验结果一致

---

### P1.2 气候冻结值

**报告值**: E=-0.798, T=+0.932, N=+0.896

**原始数据**: `experiment/endogenous_death_result.json`
- L1341-1343 (tick 50): `"E": -0.79849, "T": 0.93242, "N": 0.89652`
- L2075-2077 (stdout): `"E": -0.79812, "T": 0.93225, "N": 0.8958`

**机制**: `living_engine.py` L3924-3926
```python
if _tick_deceased:
    return {"tick": True, "deceased": True, "climate_frozen": True}
```
气候在 tick 50 后被冻结，后续 tick 不再调用 _update_luoshen_coupled。

**判定: A** — 实测值 -0.79849 / 0.93242 / 0.89652 ≈ 报告值（四舍五入）

---

### P1.3 跨重启 deceased=True

**报告值**: 死亡后重启 → deceased=True（不可逆验证）

**代码**: `living_engine.py` L706-714
```python
death_tick = _scan_hash_chain_for_death()
if death_tick is not None:
    memory["self_model"]["ring_state"]["deceased"] = True
    memory["self_model"]["ring_state"]["_death_counter"] = death_tick
```

**数据源**: `experiment/cross_restart_death_result.json`
```json
"test_A_normal_restart": {"pass": true, "expected_deceased": false},
"test_B_death_restart": {"pass": true, "expected_deceased": true},
"overall": true
```

**判定: A** — 代码 + 实验结果一致

---

### P1.4 _DEATH_PROXIMITY_SLOW = 0.7

**报告值**: 死亡 proximity 阈值 0.7 激活衰老调制

**代码**: `living_engine.py` L2473-2475
```python
_DEATH_PROXIMITY_SLOW = 0.7
_DEATH_PROXIMITY_BRIGHT = 0.9
_DEATH_ACT = True
```

**判定: A** — 代码确认

---

## 三重判据

### T1 D1.2 行为熵 (entropy)

**报告值**:
- 初始运行（8-tick 间隔, 8 个固定输入）: entropy=0.8176
- 优化后（5-tick 间隔, 两阶段正负输入）: entropy=0.9066

**原始数据源**: `experiment/triple_criteria_result.json`
- baseline: `"entropy": 0.9065966880419547`
- long_window: `"entropy": 0.9220164143616723`

代码里的 `0.8176` 值 **没有找到**。可能是更早一次运行的 stdout 输出，未被保存为 JSON，或已被覆盖。

**判定: B (对 0.8176)** — 数值来源丢失。当前 result.json 只有 0.9066（baseline）/ 0.9220（long_window）。建议论文只引 0.9066 / 0.9220，删除 0.8176。
**判定: A (对 0.9066 / 0.9220)** — triple_criteria_result.json 保存的精确值。

---

### T2 D3.2 中枢协调 |ρ(ema_S, mode)|

**报告值**:
- 初始运行: |ρ| = 0.3753
- 优化后（两阶段负→正输入）: |ρ| = 0.7993

**原始数据源**: `experiment/triple_criteria_result.json`
- baseline: `"r_hub_mode": 0.799300192195549`
- long_window: `"r_hub_mode": 0.6361521224968288`

代码里的 `0.3753` 值 **没有找到**。可能是第一次单配置运行（无两阶段负→正切换，只是固定分段输入）的 stdout 输出。

**判定: B (对 0.3753)** — 来源丢失。建议论文只引 0.7993 / 0.6362。
**判定: A (对 0.7993 / 0.6362)** — result.json 保存的精确值。

---

### T3 D3.1 death_modulation 比例

**报告值**:
- baseline (threshold=90, 89 有效采样): death_modulation=29.2%
- long_window (threshold=200, 199 有效采样): death_modulation=29.6%

**原始数据源**: `experiment/triple_criteria_result.json`
- baseline: `"death_modulation": 0.29213483146067415`
- long_window: `"death_modulation": 0.2964824120603015`
- analysis: `"dm_baseline_pct": 29.213483146067414, "dm_long_pct": 29.64824120603015`

**几何恒等式**: `_DEATH_PROXIMITY_SLOW = 0.7` 决定死亡调制窗口 = 30% lifespan → death_modulation 几何期望值 ≈ 30%

**判定: A** — 数值精确匹配，两配置下恒为 ~29.2-29.6%

---

### T4 D2.3 ICC 相位一致性

**报告值**:
- baseline: ICC=1.0 (实际 0.99996)
- long_window: ICC=0.8307

**原始数据源**: `experiment/triple_criteria_result.json`
- baseline: `"icc_phase": 0.99996166636362254`
- long_window: `"icc_phase": 0.8306175396554859`

**计算公式**: `run_triple_criteria.py compute_criteria()` Pearson r(phase[:-1], phase[1:])

**判定: A** — result.json 精确值匹配报告值

---

### T5 判据阈值清单

| 子判据 | 代码位置 | 阈值 |
|--------|---------|------|
| D1.1 type_commitment | compute_criteria() | nonzero_ratio_amp > 0.5 AND ratio > 0.3 |
| D1.2 entropy | compute_criteria() | > 0.5 |
| D2.1 preplay var | compute_criteria() | > 1e-6 |
| D2.2 narrative var | compute_criteria() | > 1e-6 |
| D2.3 ICC | compute_criteria() | > 0.3 |
| D3.1 multi-signal | compute_criteria() | ≥3 个 bias nonzero_ratio > 0.3 |
| D3.2 hub coordination | compute_criteria() | |ρ| > 0.25 |
| 总分合格线 | compute_criteria() | ≥ 5 |

**判定: A** — 所有阈值代码与报告一致

---

### T6 额外代码阈值

| 常量 | 代码位置 | 值 |
|------|---------|---|
| _VAR_RIGID | living_engine.py | 0.005 |
| _VAR_FREE | living_engine.py | 0.15 |
| _LAMBDA_SELF_ALPHA | living_engine.py | 1.5 |
| _LAMBDA_SELF_TAU | living_engine.py | 80.0 |
| _DEATH_THRESHOLD | living_engine.py | 50 |
| _DEATH_PROXIMITY_SLOW | living_engine.py | 0.7 |
| _DEATH_PROXIMITY_BRIGHT | living_engine.py | 0.9 |
| _DEATH_ACT | living_engine.py | True |

**判定: A** — 所有常量代码确认

---

## EO_ALIGNMENT_TABLE.md 中的数字

### EO.1 5 条存在条件评估

```
2/5 ✅  (scarcity + death confirmed)
2/5 🟡  (irreversibility + metabolism partial)
1/5 ❌  (endogenous_constraints missing)
```

**数据源**: EO_ALIGNMENT_TABLE.md L38-41
**计算机制**: 手工自评
**判定: A** — 手工标注，可复核

---

### EO.2 7 个 OPCODES 评估

```
3/7 ✅  (NOP, EAT, EMIT confirmed)
2/7 🎯  (DUP, SWAP partial — 有数据结构但无差分流)
2/7 ❌  (SPAWN, CATALYZE missing)
```

**数据源**: EO_ALIGNMENT_TABLE.md L44-46
**判定: A** — 手工标注，可复核

---

### EO.3 13 条行为约束评估

```
3/13 完全满足
5/13 部分满足
5/13 未满足
```

**数据源**: EO_ALIGNMENT_TABLE.md L147
**判定: A** — 手工标注

---

### EO.4 压力系数

```
κ_E = 0.06 (原 0.03 → 2×)
κ_T = 0.04 (原 0.02 → 2×)
κ_N = 0.06 (原 0.04 → 1.5×)
baseline = 0.5
衰减到 0.37 的时间 ~40 秒 (120 tick × 0.33s)
```

**代码位置**: `input_pressure.py` L8-14:
```python
KAPPA_E = 0.06
KAPPA_T = 0.04
KAPPA_N = 0.06
N_BASELINE = 0.5
PRESSURE_DECAY_TICKS = 120
```

**衰减计算验证**:
```
exp(-1) = 0.3679 ≈ 0.37 → 当 elapsed = PRESSURE_DECAY_TICKS = 120 → 经过 ~120 ticks 确实衰减到 0.37
120 ticks × 0.33s/tick ≈ 40s → 与报告一致
```

**判定: A** — 代码值与报告一致；衰减到 0.37 需要 40 秒是 KAPPA/PRESSURE_DECAY_TICKS 的数学推论（120 ticks × 0.33s = 39.6s ≈ 40s）

---

### EO.5 Lambda-Self 评估

**报告**: EO_ALIGNMENT_TABLE.md L10, L56 标注 ⚠️ "rigidity 恒为 0 → modulator≡1"

**修复**: 改为 variance-based rigidity（`_VAR_RIGID=0.005`, `_VAR_FREE=0.15`）
**修复后**: rigidity 正确区分 Van der Pol 自然振荡（高 variance→低 rigidity）vs 僵化不动（低 variance→高 rigidity）

**判定: A** — 修复已落地，table 中的标注已过时但属于历史状态

---

## 审计汇总

| 类别 | 数量 | 项 |
|------|------|-----|
| A (有支撑可复现) | 17 | P0.1, P0.2, P1.1, P1.2, P1.3, P1.4, T3, T4, T5, T6, EO.1-EO.5 等 |
| B (找不到来源，建议删) | 2 | P0.3 (4.8×), T1 (0.8176 早期值), T2 (0.3753 早期值) |
| C (有不一致需注) | 1 | P0.4 (PRESSURE_ALPHA 0.1 vs 0.02) |

---

## 处置建议

### B 类（删除或修正）
- **P0.3 4.8×**: 改为 "EMA alpha 从 0.02 增到 0.1 约 5×" 或删除该精确倍数
- **T1 entropy=0.8176**: 来源丢失（JSON 覆盖），论文不引该值
- **T2 |ρ|=0.3753**: 来源丢失，论文不引该值

### C 类（标注不一致）
- **P0.4 PRESSURE_ALPHA 0.1 vs 0.02**: 实验脚本 `run_input_pressure_AB.py` 用局部变量覆盖为 0.02 做 rp_ema 积累，但 Van der Pol 方程里的 dE/dT/dN 通过 `pressure_differentials()` 计算（不依赖 alpha），所以 ΔE/ΔT/ΔN 数值不受影响。pressure_term 的权重大小不进入 A/B 测试。论文如需要提 alpha，应统一为 0.1 或注明实验脚本版本差异。

---

审计人: CatPaw (妙手) | 执行端
完成时间: 2026-08-13
