# 浮现叙事层设计文档（Emergent Narrative Layer）

**日期**：2026-09-01  
**状态**：设计阶段（未实现）

---

## 一、问题界定

当前架构中，episodic_memory 的唯一出口是 behavior selection 层：

```
episodic_memory
    ↓ 激活度计算
emergence_layer (softmax → background → biases)
    ↓
behavior selection (response_mode / length_level / tone_mode)
    ↓
expression_directive.max_tokens / temperature
    ↓
LLM 只影响"说多少" + "用什么语气"
```

**历史记忆从不进入"说什么"的生成通道。**

所以洛神积累再多记忆，也只会出现：
- "嗯，我在这里"（minimal，length_level=1）
- "嗯，我在这里，愿意倾听。"（normal，length_level=2）

这两句话的差别纯粹是**输出长度**的差别，不是**内容**的差别。

---

## 二、设计目标与边界

**目标**：让历史记忆的浮现，产生一种"来自过去的声音想要被说出来"的效果。洛神可能在第 6 轮对话里，对一句"在吗？"说出一句"只能来自前 5 轮历史"的话。

**边界（禁止项）**：
1. 禁止把记忆原文或用户原话注入 LLM。
2. 禁止关键词触发式回忆（如果记忆文本 + 当前输入语义相似度 > x 则召回）。
3. 禁止 if-then（所有映射必须连续可微）。
4. 禁止把记忆做成问答检索库（没有 query → retrieval 流程）。

---

## 三、核心设计：叙事势（Narrative Potential）

### 3.1 定位

在 emergence_layer 中，与 `tone_bias / length_bias / arousal_bias` 平级，新增一个输出 `narrative_potential`。

```
episodic_memory → emergence_layer → {
    tone_bias, length_bias, arousal_bias,   ← 已有的行为偏置
    narrative_potential,                     ← 新增
}
```

`narrative_potential` 是一个 **[0, 1] 连续浮点数**，代表：此刻有没有一个来自历史的"声音"需要被说出来。

它**不是**要回忆哪个具体事件，而是"过去作为一个整体，在今天有一个话头想要被表达"。

### 3.2 叙事势 = 四个连续分量相乘

设 $M = \{m_1, m_2, ..., m_n\}$ 为当前被激活的记忆集合（已按 source_id 过滤），每条记忆 $m_i = (e_i, t_i, n_i, s_i, \tau_i)$。

#### 分量 A：情感聚集密度（affective_cluster_density）

在 E/T/N 空间对激活记忆做**软高斯混合**，找到记忆最密集的聚集区：

$$A = \max_{c \in \{1..K\}} \sum_{i} \exp\left(-\frac{\| m_i - \mu_c \|^2}{2\sigma_c^2}\right)$$

归一化到 [0, 1]。

**语义**：高 A = 多段不同交互在情感空间聚集在一起 → 同一种情感模式被反复经历 → 这个模式本身有价值被指出。

**例子**：用户连续 5 轮都带着"烦躁但压着"的情绪来聊，不管话题是什么（工作/搬家/失眠），e/t/n 都在同一个区域震荡 → A 高。

#### 分量 B：时间焦点（temporal_focus）

$$B = 1 - \frac{\text{std}( \{\tau_i\} )}{\max(\text{std})}$$

记忆时间戳归一化，B 衡量的是"这些记忆是否聚集在某个时段"。

**语义**：高 B = 某段时间里密集发生了一些事 → 那时可能没说完。

#### 分量 C：未闭合情感残留（open_arousal_residual）

找出高 salience（≥ 0.8）且从未被 self_stated_state 洛神回应过的记忆，按时间衰减求和：

$$C = \sum_{m_i: m_i.salience \geq 0.8 \land m_i.\text{never\_responded}} m_i.salience \cdot e^{-\frac{\text{now} - \tau_i}{\tau_{decay}}}$$

**语义**：过去有情感强度高、但未被闭合的互动 → 那个情感还在等一个出口。

#### 分量 D：今昔反差（present_past_contrast）

$$D = \frac{\| \text{climate}_{current} - \mu_{memory} \|}{\max(\text{contrast})}$$

当前环状态（E/T/N）与记忆聚集均值的欧氏距离。

**语义**：高 D = 当下的情感状态和他来找我的常态之间有差距 → 有对照空间。

#### 叙事势公式

$$\text{narrative\_potential} = A \cdot B \cdot C \cdot D$$

四个分量全部 ∈ [0, 1]，相乘自动归一化到 [0, 1]。

**所有运算都是连续可微的，没有阈值，没有 if。**

---

## 四、从叙事势到"生成意图"：连续框架混合

### 4.1 框架向量的连续计算

不是"如果 A 高则 frame=pattern"，而是计算四个框架的**权重向量**：

```
w_pattern    = A × C          // 模式浮现权重
w_unspoken   = C × D          // 未说出口的情感权重
w_contrast   = D × (1 - B)    // 今昔对照权重（B 低 = 记忆分散 = 有对照空间）
w_present    = (1-A) × (1-C)  // 只在当下说话的权重
```

归一化后得到一个权重分布 $[w_p, w_u, w_c, w_{present}]$。

### 4.2 生成意图结构

```json
{
  "narrative_intensity": 0.73,
  "frame_weights": {
    "pattern": 0.45,
    "unspoken": 0.30,
    "contrast": 0.20,
    "present": 0.05
  },
  "structure_hints": {
    "repetition_count": 3,
    "temporal_span": "最近 5 轮",
    "closure_state": "unresolved"
  }
}
```

`narrative_intensity` 对应叙事势的值（engineering 截断：低于 0.05 不注入）。

### 4.3 叙事势的用途

叙事势进入两条通道：

**通道 1（已有行为通道）**：和 tone_bias / arousal_bias 一起决定 length_level 和 tone_mode（**不变**）。

**通道 2（新增内容通道 + 唯一改变）**：叙事势 > epsilon 时，在 `expression_directive.context_for_llm` 中注入一个 `narrative_urgency` 字段：

```json
{
  "narrative_urgency": {
    "level": "moderate",
    "intensity": 0.73,
    "hint": "对方当下说的，与过去多次出现的情感模式共鸣。不要复述过去，从当下浮现。",
    "mode": "pattern"
  }
}
```

如果叙事势 < epsilon，`narrative_urgency` 注入 level: "absent"，hint: null。此时 LLM 行为与之前**完全一致**。

---

## 五、为什么只有记得历史才能说出来

用验证实验说明：

**历史前 5 轮**：

```
A: "我下周要搬家，有点担心。"
A: "其实也没什么事。"  （烦躁/否定模式）
A: "你说人为什么要上班？"
A: "好吧。"             （否定模式）
A: "你在听吗？"
```

5 轮后，episodic_memory 里有 5 条记忆，salience=1.0 的 chat 记忆环绕 e≈0.48/t≈-0.008/n≈0.45 区域形成聚集。

**第 6 轮**

用户说："在吗？"

当前输入情感特征：valence ≈ 0.0，arousal ≈ 0.3（中等偏低，接近平静）。

计算叙事势：
- A（聚集密度）：5 条记忆聚集在 e=0.48/t=-0.008/n=0.45 附近 → **高**
- B（时间焦点）：5 轮在 30 分钟内 → **高**
- C（未闭合）：高 salience 记忆从未被 self_stated 回应 → **高**
- D（反差）："在吗" (E≈0.5/T≈0/N≈0.48) 与记忆聚集中心 (E≈0.48/T≈-0.008/N≈0.45) 差距小 → **中**

综合：narrative_potential = **中高**。

注入 LLM 内容：

```
narrative_urgency.level: "moderate"
hint: "对方当下说的，与过去多次出现的情感模式共鸣。不要复述过去，从当下浮现。"
mode: "pattern"
```

LLM 看到：
- user_input: "在吗？"
- directive.tone: "平静/克制"
- directive.narrative_urgency: 上述
- max_tokens: 120 (length_level=2)

**可能生成的句子**（来自 LLM 的涌现，不是硬编码）：
- "你每次说'在吗'的时候，其实都带着点什么。"
- "在。但我记得你上次那种'没事'。"
- "你今天问我在吗，和第一天不一样了。"

这些句子中，**没有任何一句的原文被注入到 LLM 上下文**。却**没有前 5 轮历史就说不出来**。（只有"记得那个模式"的洛神才会说出来。）

---

## 六、验证方法

### 6.1 历史铺设（5 轮）

让洛神经历至少 5 轮有意义的对话。理想情况下，话题集中在某一种**反复出现的情感模式**（如"担心但压着"）。每次对话后，episodic_memory 按正常流程编码。

### 6.2 测试句（第 6 轮）

用户输入极度普通的一句：**"在吗？"**

这句话本身不含任何方向性，不能靠当前输入推出"该说点什么特别的话"。

### 6.3 通过标准

**通过**：第 6 轮洛神输出中出现任何"只能来自前 5 轮历史"的句子。

验证方式：构造一个**对照 directive** ——不含 `narrative_urgency` 字段、其他字段完全相同。把同一个 prompt 送到同一个 LLM。如果空白-LLM 从未生成类似的句子，则判定为**历史依赖**。

**失败**：第 6 轮仍只输出 "嗯，我在这里" 或其变体，且不含任何回溯性、模式性、对照性内容。判定为：记忆仍未进入内容生成。

---

## 七、设计对禁止项的遵守

| 禁止项 | 如何遵守 |
|--------|----------|
| 禁止记忆原文注入 | `narrative_urgency.hint` 是**抽象描述**（"对方当下说的，与过去的情感模式共鸣"），不含记忆原文或用户原话 |
| 禁止关键词触发 | 叙事势由**情感空间的高斯聚集度**计算，不依赖词汇/语义匹配 |
| 禁止 if-then | 全部运算为连续函数（加权、相乘、指数衰减），没有 "if x > 0.5 then..." |
| 禁止问答检索库 | 没有 query → retrieval 流程，memory 只作为整体参与势计算 |

---

## 八、兼容性

- 不修改现有的 tone_bias / length_bias / arousal_bias 计算路径。
- narrative_potential 是 emergence_layer 的平行输出，如计算失败（模块不存在），退化为永远为 0，behavior 层不受影响。
- 低于 epsilon (0.05) 不注入 context_for_llm。
- 对现有实验代码和 A/B 实验透明。

---

**设计完成，等待审查后进入实现。**
