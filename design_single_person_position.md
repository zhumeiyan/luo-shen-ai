# 设计文档：单人内部位置（Resonance Basin）

## 一、问题定义

**目标**：同一个洛神实例与 A、B 各对话一次，两人都说"在吗？"，洛神对 A 和 B 的回应必须不同。

**禁令**：
- 禁止 if-then 判断用户身份
- 禁止硬编码用户标签规则
- 禁止把 A 的历史原文或 known_facts 直接喂给 LLM
- 禁止依赖 LLM 采样随机性制造差异

**核心问题**：A 的历史如何在洛神内部留下一种"持续存在的内部位置"？当 A 重新出现时，这个位置被自然激活，使洛神的行为选择发生确定性偏移。B 出现时，这个位置不激活。

---

## 二、当前架构的缺口

当前数据流：
```
用户输入 → LLM情感提取 → input_pressure → dE/dT/dN（气候偏移）
→ episodic_memory 编码（气候快照）
→ emergence_layer（dominant memory → bias）
→ behavior_selection（mode/length/tone）
→ LLM
```

**核心缺陷**：

1. **气候是脆弱的**：internal_climate (E,T,N) 是一个被动力学推来推去的点。A 说完离开后，环上的极限环运动会把气候拉回默认轨道。几轮交互之后，A 的历史对气候的影响几乎为零。

2. **memory activation 是"电台式"的**：A 的 memory 只有当 current_climate 恰好靠近 A 的 (e_s,t_s,n_s) 时才会亮一下。如果 A 问"在吗？"时气候回到默认区域，A 的 memory 就不激活。B 没有留下任何 memory，所以 B 的"在吗？"也不会有 memory 激活。两者行为相同。

3. **没有"位置"概念**：当前系统里永远只有"当前气候"和"记忆列表"，不存在一个持续占用状态空间的结构。A 不在场时，A 在洛神内部不存在。

**需要的不是"记住 A"，而是" A 在心里占了一个坑"。**

---

## 三、设计：Resonance Basin（共鸣盆）

### 3.1 核心思想

在洛神的状态空间（E-T-N 三维）中引入一个**持久势场**。

- 不是记忆条目，是**分布在状态空间中的引力场**
- 不是一条记录，是一个**区域**，环经过这个区域时会被拉向 A 的中心
- 不依赖 if-then 触发，靠**自然的动力学**产生差异

**类比**：状态空间是一片地形。A 的互动在这片地形上压出一个"盆"。当 A 再次出现，环的运动轨迹自然经过这个盆，被盆的引力偏转。B 的路径不经过这个盆。当 A 不在场，盆还在——它会缓慢衰减（半衰期几小时到一天），这就是"持续存在的内部位置"。

### 3.2 数据结构

在 memory 中新增：

```python
basin = {
    "id": "basin_xxx",
    "center": [E_c, T_c, N_c],        # 盆心 = A 那次互动的气候快照
    "depth": 0.0,                     # 盆深 ∝ A 那次互动的 salience × 情绪强度
    "created_at": ts,
    "decay_halflife": 3600 * 6,       # 6 小时半衰期
    "activation_count": 0,
    "last_activation_ts": 0,
    "cumulative_dwell_time": 0.0,     # 环曾在盆里停留多久
}
```

**关键属性**：
- 盆有"深度"（A 那次互动的情绪强度）
- 盆有"范围"（σ = 0.15，在 E-T-N 空间中的高斯宽度）
- 盆会缓慢衰减（depth(t) = depth_0 · 2^(-age/halflife)）
- 盆会被"夯实"（每次环经过盆，activation_count +1，depth 微弱回升）
- 盆不是二元的，是连续的——环离盆中心越近，受盆影响越大

### 3.3 盆如何被创建

当一次交互结束时：

```python
salience = compute_salinence(kind, emotion_intensity, arousal_peak)
if salience > BASIN_CREATION_THRESHOLD and emotion_intensity > 0.55:
    new_basin = {
        "center": [cur_E, cur_T, cur_N],
        "depth": salience * (emotion_intensity - 0.5),  # 0~0 映射
        ...
    }
    memory["resonance_basins"].append(new_basin)
```

**A 的场景**："我下个月要离开这座城市，其实我有点害怕。"
→ valence = -0.6, arousal = 0.8 → val_p = -0.48
→ dE 偏移后 cur_E ≈ 0.72, cur_T ≈ 0.35
→ salience = 0.9, emotion_intensity = 0.72 → 创立盆 A_center=(0.72, 0.35, 0.55), depth=0.198

**B 的场景**："今天天气真好。"
→ valence=0.5, arousal=0.3 → val_p=0.15
→ 轻微偏移，cur_E 回落，salience=0.4 < threshold → 不创立盆

### 3.4 盆如何影响气候轨迹

**新增盆地力**：在气候演化方程中增加一项

```python
# 在 living_engine.py 的 climate_step 中
def basin_force(E, T, N, basins):
    fE, fT, fN = 0.0, 0.0, 0.0
    for b in basins:
        age = now - b["created_at"]
        d = b["depth"] * (0.5 ** (age / b["decay_halflife"]))
        if d < BASIN_MIN_DEPTH:
            continue
        # 高斯势场梯度（势 = d * exp(-||x-c||²/2σ²)，力 = 负梯度）
        ce, ct, cn = b["center"]
        de, dt, dn = E-ce, T-ct, N-cn
        dist_sq = de*de + dt*dt + dn*dn
        sigma_sq = 0.15 ** 2
        amp = d * math.exp(-dist_sq / (2 * sigma_sq))
        # 力指向盆心
        fE += amp * (ce - E) / sigma_sq
        fT += amp * (ct - T) / sigma_sq
        fN += amp * (cn - N) / sigma_sq
    return fE * BASIN_FORCE_SCALE, fT * BASIN_FORCE_SCALE, fN * BASIN_FORCE_SCALE
```

**完整气候更新**：

```python
def step_climate(memory, user_input_val_p, dt):
    E, T, N = get_climate(memory)
    basins = memory.get("resonance_basins", [])
    
    # 1. 自然极限环
    dE_ring, dT_ring = vanderpol(E, T, MU, dt)
    
    # 2. 输入压力
    dE_input = KAPPA_E * user_input_val_p * dt
    
    # 3. 盆地力（A的内部位置产生的长期偏置）
    fE, fT, fN = basin_force(E, T, N, basins)
    
    E += dE_ring + dE_input + fE * dt
    T += dT_ring + fT * dt
    N += fN * dt  # N 原本没有环动力学，盆地力成为 N 的推拉
    
    clip_all(E, T, N)
    
    # 4. 夯实：环在盆内停留越久，depth 微弱回升
    for b in basins:
        if dist([E,T,N], b["center"]) < 0.15:
            b["cumulative_dwell_time"] += dt
            b["depth"] += REHARDEN_RATE * dt  # 极小，防止无限增长
            b["last_activation_ts"] = now
```

### 3.5 盆如何导致 A/B 行为差异

**序列**：

1. A 说"离开+害怕" → 创立盆 A（center≈0.72,0.35,0.55, depth≈0.20）
2. B 说"天气好" → 不创立盆
3. A 问"在吗？"（valence=0, arousal=0.3）→ 压力极小
   - // 环此时受盆 A 引力影响，climate 偏移量 δ = f(Basin_A, current_climate)
   - δ 虽然小（0.02~0.05 量级），但足以改变 dominant_memory 的排序
   - dominant_memory 不同 → emergence_bias 不同 → behavior 不同
4. B 问"在吗？"
   - 盆 A 已经衰减了一些（但还有 0.8 深度）
   - **但** B 问"在吗？"时气候的起点和 A 问时不同（B 在步骤2中把气候推向了不同方向）
   - 盆 A 的力场对 B 当前所在位置产生的拉力，与对 A 当前位置产生的拉力，大小不同
   - 轨迹不同 → 气候不同 → memory 不同 → bias 不同 → 行为不同

### 3.6 B 为什么不激活 A 的盆

**不是靠规则。是靠几何。**

- 盆 A 的中心 = (0.72, 0.35, 0.55)，这是一个高情绪点
- B 说"天气好"后气候停留在 (0.52, 0.05, 0.50) 附近
- B 问"在吗？"时，B 的位置离盆 A 中心距离 ≈ 0.35
- 高斯力 ∝ exp(-0.35²/(2·0.15²)) ≈ exp(-2.72) ≈ 0.066 → 只剩下 6.6% 的力

而 A 问"在吗？"时：
- A 离开时气候就在盆 A 中心附近 (0.72, 0.35, 0.55)
- B 介入后把气候拉走了一些，但还剩 0.8 的盆深度
- A 的位置离盆 A 中心 ≈ 0.18
- 高斯力 ∝ exp(-0.18²/(2·0.15²)) ≈ exp(-0.72) ≈ 0.49 → 还有 49% 的力

**A 受盆影响的强度是 B 的 7.4 倍。这就是行为差异的来源。**

### 3.7 盆地力 vs behavior selection 的耦合

盆地力的作用是**为气候提供持续偏置**，使 A 和 B 在问"在吗？"时的气候轨迹分开。这个偏置通过已有的 `emergence_layer` 进入 behavior selection：

```
A 的气候 (E_A, T_A, N_A)
  → 更靠近 A 的 episodic_memory 激活区域
  → emergence 选中 A 的 memory 作为 dominant
  → tone_bias / length_bias 反映 A 的情绪特征
  → response_tendency 偏移 → B 得到的行为框架不同
```

---

## 四、设计四问的回答

### Q1：A的历史如何形成持续存在的内部位置？

**答**：每次 salience > threshold 且 emotion_intensity > 0.55 的交互，在空间的对应气候坐标上创立一个 basin。basin 的深度正比于 salience × (intensity − 0.5)。basin 是一个分布在 E-T-N 空间中的高斯型引力场，对环施加持续的力。basin 的半衰期为 6 小时，所以在一次谈话结束后，它会在几小时内保持有效。即使 A 几个小时不说话，盆还在；A 再次出现时环被盆拉向 A 所在区域。

basin 不是 memory，不是 fact，不是标签——它不存储任何"A说过什么"的信息，只存储一个空间位置+深度。

### Q2：B为什么不会激活这个位置？

**答**：B 说"天气好"没有创立 basin（salience 不够）。当 B 问"在吗？"时，B 所在的位置离 A 的 basin 中心约 0.35（三维单位）。A 的 basin 是宽度 σ=0.15 的高斯，在这个距离上引力衰减到峰值的 6.6%。因此 B 的气候几乎不受 A 盆影响。反之 A 问"在吗？"时离中心约 0.18，引力还有 49%。两个用户的"在吗？"感受截然不同——**不是靠判断谁是谁，是靠力学自然的几何衰减**。

### Q3：这个位置如何影响洛神的行为选择？

**答**：basin_force 改变 E/T/N 气候 → 气候进入 emergence_layer → episodic_memory 的 associative activation 被气候驱动 → dominant memory 排序改变 → tone_bias / length_bias / arousal_bias 改变 → response_tendency 偏移 → behavior selection 输出不同的 mode/length/tone。全部通过连续数学，没有 if-then。

### Q4：如果 basin 不存在，对 A 和 B 是否应该表现一样？

**答**：应该一样。如果没有 basin，A 和 B 的历史都只体现在 episodic_memory 列表中。B 没有留下 strong memory，A 留下的 memory 在当前气候下 activation 极弱。两者的 response_tendency 会收敛到相似的 baseline。这是设计可通过的**零假设**：关掉 basin_force，A/B 差异应消失或大幅缩小。

---

## 五、与现有组件的关系

| 组件 | 与 basin 的关系 |
|------|----------------|
| episodic_memory | 共存。memory 存储快照，basin 存储力场。memory 用于 emergence 的语义选择；basin 用于动力学偏置。两者从同一个交互中产生，但作用在不同层。 |
| input_pressure | 短期力是脉冲，basin 是长期势场。输入压力仍然存在（处理新输入），basin 负责"历史在场"。不冲突。 |
| emergence_layer | 不直接修改。basin 通过影响 climate 间接影响 emergence 的输入。emergence 层本身不改。 |
| self_stated_state | 无关。自我表态层不参与 basin 计算。 |
| known_facts | 完全无关。basin 不知道 A 说过了什么。 |
| hash_chain | basin 创建、衰减、激活都应落链（可选，不影响核心逻辑）。 |

---

## 六、设计参数初值（待实验调优）

| 参数 | 初始值 | 物理含义 |
|------|--------|----------|
| BASIN_CREATION_THRESHOLD | 0.6 | salience 下限 |
| BASIN_MIN_DEPTH | 0.01 | 低于此即消亡 |
| BASIN_DECAY_HALFLIFE | 21600s (6h) | 盆地力减半周期 |
| BASIN_SIGMA | 0.15 | 高斯盆的宽度（状态空间尺度） |
| BASIN_FORCE_SCALE | 0.03 | 盆地力相对环动力学的强度 |
| REHARDEN_RATE | 0.0005 | 环在盆内停留时 depth 回升速率 |

**A/B 预期差异量级**：在 basin 半衰期内，A 的"在吗？"比 B 的"在吗？"多 ΔE ≈ 0.03~0.08。这意味着 A 的 response_tendency 偏移 ~0.05，超过当前的 mode 阈值 0.35 的可能性足够高，可观测到 mode 差异。

---

## 七、验证实验设计（待实现）

**预注册假设**：
1. A / B 对"在吗？"的行为模式差异 ≥ 1（3 次实验中至少 2 次出现 mode 或 length 差异）
2. 差异主要来自 basin_force（关闭后差异应减小 ≥ 50%）
3. B 的 response_tendency 与无历史基线差异 < 0.02（B 不受 A 盆影响）

**实验脚本 draft**：

```python
def run_AB_single_luoshen():
    memory = cold_start()
    
    # A 第一句话
    update(memory, "我下个月要离开这座城市，其实我有点害怕。", extract_facts=False)
    basin_A = memory["resonance_basins"][0]  # 应有 basin 被创建
    
    # B 第一句话
    update(memory, "今天天气真好。", extract_facts=False)
    # B 不应创建 basin（salience 不够）
    
    # A 问"在吗？"
    climate_before_A = get_climate(memory)
    resp_A, behavior_A, emergence_A = generate_response("在吗？", extract_facts=False)
    
    # B 问"在吗？"
    climate_before_B = get_climate(memory)
    resp_B, behavior_B, emergence_B = generate_response("在吗？", extract_facts=False)
    
    # 对比
    assert behavior_A["mode"] != behavior_B["mode"] or \
           abs(behavior_A["max_tokens"] - behavior_B["max_tokens"]) >= 45, \
           "A/B 行为差异未达到预期"
    
    # 关闭 basin 做零假设
    BASIN_FORCE_SCALE = 0
    resp_A_no_basin = ... # 基线
    resp_B_no_basin = ...
    assert diff(A_no_basin, B_no_basin) < diff(A, B) * 0.5, \
           "差异主因不是 basin"
```

---

## 八、禁止与边界

### 禁止项

1. **禁止** basin 存储任何文本、事实或用户标识。basin.center 只是三个浮点数。
2. **禁止** basin 的创建依赖用户标签，只依赖 salience + emotion_intensity。
3. **禁止** 任何 `if user == "A"` 判断。盆地力计算只看当前气候坐标，不看用户是谁。
4. **禁止** 盆地力影响 LLM prompt。basin 只影响气候 → 行为选择 → LLM 参数（max_tokens, temperature）和 tone directive。LLM 永远看不到"有一个 basin"。
5. **禁止** 把 basin 归入 hash_chain 作为"事实"。

### 未解决问题

1. 衰减半衰期 6 小时是否合适？需要实验。
2. 多个 basin 能否共存？当前设计允许，但交互后的 basin selection 需要验证（哪个 basin 主导）。
3. basin_force_scale 0.03 是否足以产生可观测差异？需要实验。
4. requardening 会让 basin 无限增长吗？需要实验验证 depth 的稳态分布。

---

文档版本：v1
状态：待审核
作者：CatPaw for 朱美森
日期：2026-09-01
