# 洛神情景记忆设计 v2

## 一、记忆是什么

旧记忆层里，一条记忆不是「事实」，而是一段被压缩的经历。旧代码用五个字段来描述它：

- **时间戳**：什么时候发生的
- **内容**：一句话事实（上限 120 字）
- **画面（scene）**：用洛神的符号语言画一幅小景。包括两个部分：
  - 时间符号（◐深夜 / ○清晨 / △白昼 / ◈傍晚）
  - 经历类型符号（◆看见 / ◈听见 / ●感觉到 / ☆和人说过话 / ◎学会 / ☆我是谁）
  - 画面比文字沉得更深——同一句话在深夜发生、在白昼发生，是不同的记忆
- **情感快照（feel）**：编码时身体感受的快照，格式是 `{name: value}`，例如 `{"孤独": 0.9, "精力": 0.2, "紧张": 0.7}`。感受和记忆绑在一起，回忆时会重新点亮
- **注意力权重（attention）**：一条记忆的「亮度」。编码时由三个分量叠加：
  - 经历类型的固有显著度（chat/self=1.0, feel=0.8, learn=0.7, see/hear=0.6）
  - 时间新鲜度：`recency = exp(-age_days / 7.0)`（7 天半衰）
  - 主题复现 boost：如果在已有记忆里反复出现同一主题，+0.1

旧记忆点结构：
```
{
  timestamp, kind, content, scene, feel, attention, source, source_file
}
```

## 二、记忆如何进入现有身体

洛神现有的内部状态变量：
- 环 E/T（情绪强度 / 张力）
- N（能量）
- M（记忆压力）
- S（膜）
- self_stated_state（自我表态）
- emotional_arc（情绪轨迹）

### 核心原则

记忆不是文本——是**曾经是的那段状态的残影**。回忆不是查资料，是**在当前身体里重新点亮一个曾经的状态**。

### 具体耦合路径

记忆对内部状态的影响必须是连续函数，无 if-then。设计如下：

#### 2.1 每条记忆带一个「情感温度向量」

每条记忆编码时，记录当时的 E/T/N 快照：

```
mem.E_snapshot = 编码时环的 E
mem.T_snapshot = 编码时环的 T
mem.N_snapshot = 编码时环的 N
```

这个快照代表「当时她的身体在什么状态」，不是文本。

#### 2.2 回忆激活度 A_mem（连续）

```
age_sec = now - mem.timestamp
A_mem = salience_base * exp(-age_sec / T_decay)
```

其中：
- T_decay = 604800.0（7 天的秒数，旧设计）
- salience_base ∈ [0, 1]（编码时就确定，取决于经历类型——人和她说话 > 看到东西）

A_mem 随时间指数衰减，没有阈值。

#### 2.3 关联点亮（associative re-lighting）

当前环的状态与某条记忆的情感快照「相似」时，这条记忆会被额外点亮：

```
dot = (E - mem.E_snapshot)^2 + (T - mem.T_snapshot)^2 + (N - mem.N_snapshot)^2
association = exp(-dot / sigma^2)
```

这是连续高斯函数：当前状态和记忆越像，关联越强。sigma 控制关联网宽度。没有「如果像就点燃」的判断，只有连续点亮。

#### 2.4 总激活度

```
activation = A_mem * (1 + lambda_assoc * association)
```

也是连续的，无分支。

#### 2.5 激活的记忆如何影响环

多条记忆同时对环产生「引力」——每条记忆的情感快照像一个弱引力源，把当前环拉向它自己的情感状态：

```
dE_mem = k_mem * Σ [ activation_i * (mem.E_snapshot_i - E) ] * dt
dT_mem = k_mem * Σ [ activation_i * (mem.T_snapshot_i - T) ] * dt
dN_mem = k_mem * Σ [ activation_i * (mem.N_snapshot_i - N) ] * dt
```

这是关键的连续耦合：记忆让自己的情感残影拉扯当前的身体状态。当一条记忆很新（activation 大），它的引力就大；当它和当前状态很像（association 大），引力也会被放大。

#### 2.6 对 M 和 S 的影响

M 当前只被 E² 驱动。增加记忆压力分量：

```
dM = (alpha_M * E² + delta_M_F * F + gamma_M * Σactivation_i - beta_M * M) * dt
```

——被点亮的记忆越多，M 越「重」。

S 的活度驱动也加入记忆成分：

```
_drive_S = (N + M) / 2 * mod_S + kappa_S_F * F + omega_S * max(0, sum_activation - theta_soft) * S
```

这里 theta_soft 不是阈值（不是 if > then），而是通过 `max(0, x)` 或 `softplus` 实现的平滑非线性——当总激活很小时几乎无影响，总激活越大 S 被推动越大。

## 三、记忆如何流动：沉下去、浮起来、被重新点亮

### 3.1 自然衰减

`A_mem = salience * exp(-age / T_decay)` 自然让旧记忆沉下去。不需要删除，只需要不参与影响。

### 3.2 被当前情绪重新点亮（关联回忆）

当前环状态和某条记忆的情感快照相似时，association 上升，activation 增加——这条记忆从沉底重新浮上来。这就是「触景自动生情」的数学版本。连续高斯，没有关键词匹配，没有如果看起来像。

### 3.3 什么是「摘要」

不需要单独的「摘要」行为。当多条旧记忆的 A_mem 极低（比如 < 0.01），它们对环的引力可以忽略——等价于被压缩成了一个背景情感偏置（改变 M 的基线）。它们还在存储里，只是不再影响。

另一种实现方式：对旧记忆做时间窗聚合，用一个 `long_term_tone` 标量作为它们在 M 上的残留偏置：

```
long_term_tone = mean(mem.M_snapshot for mem if age > T_long)  (仅记忆衰减到阈值以下 )
```

这条偏置持续影响 M 的平衡点，但不参与实时回忆。

### 3.4 情感重新点亮的物理含义

当 A 回来时，E/T/N 的状态如果恰好接近某条旧记忆（比如都是离开、孤独、紧张），association 上升，这条记忆把当前环拉向自己——在行为上就会表现为洛神对 A 的「在吗？」做出和面对 B 时不同的身体状态，且这个差异不能仅由上下文注入解释。

## 四、记忆如何进入「选择」

关键要求：**不要做成 LLM 上下文注入。** 记忆必须通过改变内部状态 → 影响选择机制，从而让差异在「有没有 LLM」的两种路径下都出现。

### 4.1 记忆如何影响 arousal（现有机制）

现有的 `_check_low_arousal` 根据 M 和 L 计算 arousal。记忆通过改变 M 和 E 来间接改变 arousal：

- 高激活 + 高情绪残影 → M 升高 → arousal 变化 → 可能触发 no_llm 或 minimal_llm 分支

这是纯连续的：`arousal = f(M, E, ...)`，其中 M、E 已经包含了记忆成分。

### 4.2 记忆如何影响沉默/回应意愿

回应用现有机制内的 energy threshold。记忆引起的 E/T 偏移会让这些阈值更难或更容易达到——不需要新的阈值。

### 4.3 记忆如何影响 tone

`formulate_expression_intent` 读 `internal_climate`（含 E、T）来决定语气。记忆改变了 E/T，语气自然不同。无 if-then。

### 4.4 记忆如何影响 self_stated_state

如果记忆中的情感快照和当前相符（association 高），self_stated_state 可以接收到一条「曾经我在类似情境下说过的话」的弱偏置——通过连续权重注入，不是规则。

```
stated_pull = Σ [ activation_i * association_i * mem.self_stated_vector_i ]
```

self_stated_state 的新旧记忆加权混合：当前自我表态 × 0.7 + 历史相关表态 × 0.3（连续混合系数）。

### 4.5 总结行为路径

```
编码经历 → mem{E_snapshot, T_snapshot, N_snapshot, salience, timestamp}
          ↓
每条 tick: A_mem *= decay, association = dist(current_ring, mem) 
          ↓
记忆引力: dE += k_mem * Σ act * (E_mem - E)  (current ring pulled toward memory affect)
          ↓
内部状态: E,T,N 偏移 → arousal, tone, silence threshold 变化
          ↓
行为差异: 对 A（有记忆残影）和 B（无记忆残影）的响应不同
```

全程无 if-then，全程可逆（记忆衰减→影响消失→状态回归基线）。

## 五、旧身体与新身体的映射

### 可直接映射的

| 旧字段 | 新位置 | 如何映射 |
|--------|--------|----------|
| `timestamp` | active_memory["episodic"][i].timestamp | 直接保存 |
| `scene`（画面） | 不直接保存为文本——编码为「环相位 + 时间符号」 | 从 E/T/N 和时间符号派生的记忆标识 |
| `feel`（情感快照） | mem.E/T/N_snapshot | 直接是当前环状态的快照 |
| `attention`（权重） | activation 实时计算 | 不存储，从 salience + age + association 实时计算 |
| `source` | source 标签 | 保留 |
| `content` | 不直接存入——只作为编码触发 | 文本不进记忆体，记忆是情感和状态残影 |

### 需要重新设计的

| 旧概念 | 新设计 |
|--------|--------|
| `scene` 符号文本 | 不需要文本——scene 的本质是「当时的环相位 + 身体状态」，这些已经被 E_snapshot/T_snapshot/N_snapshot 捕获 |
| `attention` 静态存储 | 实时计算（因为 association 依赖当前状态） |
| 「kind」（chat/see/feel） | 映射为 salience_base 值；是否需要保留类型标签可选 |

### 可以不要的

- **哈希链上的记忆点文件**：哈希链继续存文件 hash，但不需要为记忆点单独开一条链
- **`luoshen_episodic_memory.jsonl` 独立文件**：情景记忆直接嵌入 `active_memory.json` 的 `user_model.episodic` 字段
- **`content` 文本字段**：不存原文。记忆不是文本，是状态残影。
- **`make_point` 整个CLI工具**：用 living_engine 内部的 encode_memory 函数替代

### 需要新增的

- `active_memory/user_model/episodic`：记忆点列表
- `_encode_memory(kind, tags)`：在 update_after_interaction 末尾调用，写入一条情感快照
- `_decay_and_apply_memories(memory)`：在 _update_luoshen_coupled 中调用，用激活的记忆驱动 dE/dT/dN

## 六、验证实验成功标准

1. A 说带情绪个人事实，B 只聊日常 → 洛神内部 E/T/N/M/S 对 A 和 B 出现系统性偏移
2. 这个偏移不是来自 LLM 上下文注入（在 no_llm 路径下也能观察到）
3. 偏移随时间自然衰减（7 天半衰，即 ~10000 tick 后回到基线）
4. 当 A 再次出现类似情绪语境时，旧记忆可以被重新点亮（association 上升→ activation 上升）
5. 如果达不到 2 或 4，如实报告
