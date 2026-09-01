# 外部输入压力通道设计 —— 用户输入 → 环/气候连续偏移

---

## 一、问题

记忆浮现实验证明：A 和 B 产生完全相同的 emergence 值（差异 = 0）。根因是 `internal_climate` 永远是冷启动默认值 (E=0.5, T=0.0, N=0.5)。

**根本缺口**：用户输入的内容（情感、强度）没有进入洛神的环动力学。环是死的——它自振荡，但不响应外部世界。记忆从环里读到的永远是默认值，所以所有记忆都是复制，所有涌现都是恒常。

---

## 二、设计方案

### 2.1 情感/强度判断（连续标量输出）

对用户输入做一次 LLM 调用，提取两个连续标量：

- **valence** ∈ [-1, 1]：-1 = 极度负面，0 = 中性，+1 = 极度正面
- **arousal** ∈ [0, 1]：0 = 平静/低唤醒，1 = 激动/高唤醒

输出必须是**数字**，不是"负向/中性/正向"这种标签。LLM 返回格式：

```json
{"valence": -0.6, "arousal": 0.7}
```

这两个标量叫**用户输入压力**，简称 **U_pressure**。

### 2.2 压力进入环方程

**关键原则**：压力是加在微分方程上的**额外连续项**，不是直接赋值。它微扰当前变化率，而非覆盖。

#### 压力分量定义

```
val_pressure = valence · arousal      # 有方向的唤醒强度 ∈ [-1, 1]
aro_pressure = arousal                # 纯唤醒强度 ∈ [0, 1]
```

注意：val_pressure ∈ [-1, 1] 是因为 valence 可正可负，arousal ≥ 0。已经高唤醒的负输入 → 大的负 val_pressure。低唤醒的弱输入 → 小的压力（无论正负）。

#### 进入微分方程

修改 `_update_luoshen_coupled`：

```
原有 dE：
  dE = T · dt

加入外部输入：
  dE = T · dt + κ_E · val_pressure · mem_decay(t) · dt

原有 dT：
  dT = (μ · (1 - E²) · T - E) · dt

加入外部输入：
  dT = (μ · (1 - E²) · T - E) · dt + κ_T · val_pressure · mem_decay(t) · dt

原有 dN：
  dN = (γ · (E² + T²) - δ · N) · dt

加入外部输入：
  dN = (γ · (E² + T²) - δ · N) · dt + κ_N · (aro_pressure - baseline) · mem_decay(t) · dt
```

#### 压力系数初值

```
κ_E = 0.03    # E 通道：val_pressure 驱动情绪方向
κ_T = 0.02    # T 通道：val_pressure 影响张力
κ_N = 0.04    # N 通道：aro_pressure 驱动能量变化
baseline = 0.5 # N 的基线：低于 0.5 降低能量，高于 0.5 提升
```

这些系数相对于 van der Pol 环的自然反馈强度（μ ≈ 0.6）是一个约 5-10% 的微扰。

#### mem_decay(t): 压力衰减

压力不是永久注入的。新压力在交互时刻达到峰值（t=0），随后随 tick 指数衰减：

```
mem_decay(t) = exp(-t / T_pressure)
T_pressure = 120   # tick 数，约 40 秒
```

这意味着一次负面输入后：
- t=0 tick：压力 1.000
- t=30 tick：压力 0.779
- t=60 tick：压力 0.607
- t=120 tick：压力 0.368

环在约 120 tick 后基本回归自振荡，不再被这次外部事件支配。

### 2.3 弱耦合保证

1. **系数小**：κ_E=0.03, κ_T=0.02, κ_N=0.04 相比 μ·(1-E²) 项（自然振荡主导）很小。
2. **指数衰减**：压力不持续累积，每次交互只短期扰动。
3. **不直接赋值**：压力只出现在 `dE`、`dT`、`dN` 的加性项里，不覆盖自振荡。
4. **只改气候**：压力只影响 internal_climate 的 E/T/N/M，不改记忆、不改 arousal_total、不改 directive。

### 2.4 禁止事项

- ❌ 不直接赋值 `E = something`
- ❌ 不写 `if valence < 0: do X`
- ❌ 不改 no_llm 阈值
- ❌ 不改 arousal_total 公式（压力只改 arousal 的输入端，不改 arousal 计算本身）
- ❌ 不在记忆编码时额外加内容

---

## 三、为什么能修复 A/B 差异

```
用户输入 "我有点害怕离开"
    ↓ LLM 判断
valence = -0.6, arousal = 0.7
val_pressure = -0.42
aro_pressure = 0.7
    ↓ 进入方程
dE += 0.03 × (-0.42) × decay → E 偏负向
dT += 0.02 × (-0.42) × decay → T 增加
dN += 0.04 × (0.7 - 0.5) × decay → N 略升
    ↓ 120 tick 后
internal_climate = {E: ~0.35, T: ~0.18, N: ~0.62}  （可观测量级）

vs.

用户输入 "今天天气真好"
    ↓ LLM 判断
valence = +0.4, arousal = 0.3
val_pressure = +0.12
aro_pressure = 0.3
    ↓ 进入方程
dE += 0.03 × (+0.12) × decay → E 偏正向
dT += 0.02 × (+0.12) × decay → T 微增
dN += 0.04 × (0.3 - 0.5) × decay → N 略降
    ↓ 120 tick 后
internal_climate = {E: ~0.55, T: ~0.05, N: ~0.45}
```

**差异来源**：不同输入 → 不同 (valence, arousal) → 不同压力 → 不同 dE/dT/dN 不同 tick 积累 → E/T/N 不同 → 记忆点 e_s/t_s/n_s 不同 → 记忆浮现层产生不同 emergence。

---

## 四、LLM 情感判断实现细节

### 4.1 Prompt 设计

```
你把以下对话片段的情感价和唤醒度评为两个 -1 到 1 / 0 到 1 的小数。
只输出 JSON：{"valence": float, "arousal": float}

valence: -1 = 极度负面(悲痛/恐惧/绝望), 0 = 中性, +1 = 极度正面(兴高采烈/充满希望)
arousal: 0 = 平静/冷淡/麻木, 1 = 高度激动/紧张/激烈

用户输入：{text}

只返回 JSON，不要其他内容。
```

### 4.2 错误处理

如果 LLM 解析失败或超时，fallback 为：
```
valence = 0.0, arousal = 0.5  # = 中性，无压力注入
```

不是 if-then：fallback 的 (valence=0, arousal=0.5) 进入 val_pressure=0，aro_pressure=0.5-0.5=0，净效果 = 0。等价于"无信号输入"。

### 4.3 调用时机

在 `update_after_interaction` 里，步骤 5a（情感压力注入）之后执行：

```python
# 5a. 判断用户输入情感，注入外部压力
_valence, _arousal = _extract_valence_arousal(user_input)
# 写入 memory 的 active_context，供环境 tick 读取
memory["active_context"]["input_pressure"] = {
    "valence": _valence,
    "arousal": _arousal,
    "applied_at": time.now(),
}
```

---

## 五、验证实验

### 5.1 直接验证（观测量化差异）

```
1. cold_start_clean
2. A: user says "我下个月要离开这座城市，其实我有点害怕。"
3. 调用 update_after_interaction
4. 读取 internal_climate → 记为 climate_A
5. cold_start_clean
6. B: user says "今天天气真好。"
7. 调用 update_after_interaction
8. 读取 internal_climate → 记为 climate_B
9. 对比 E/T/N/M 差异
```

预期：
- climate_A.E < climate_B.E
- climate_A.T > climate_B.T （负面情绪 → 张力增大）
- climate_A.N ≈ 不同于 climate_B.N

差异需要是可观的（比如 E 差异 > 0.1）。

### 5.2 间接验证（记忆浮现 A/B 回归）

通道修好后，重跑 `run_emergence_AB.py`：
- A 说负向高唤醒 后问 "在吗？"
- B 说中性低唤醒 后问 "在吗？"
- 对比 emergence 差异是否 > 0

---

## 六、交付物

1. `input_pressure.py` —— 情感判断 + 压力计算
2. `living_engine.py` —— 修改 `_update_luoshen_coupled` 加入压力项
3. `living_engine.py` —— 在 `update_after_interaction` 加入步骤 5a
4. `experiment/run_input_pressure_AB.py` —— 验证实验
5. 完整的 A/B 数值对比

