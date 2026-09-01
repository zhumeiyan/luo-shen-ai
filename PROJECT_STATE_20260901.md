# 洛神项目状态档案

**日期**：2026-09-01

> ⚠️ **红线规则**：`hash_chain_gateway.py` 是哈希链唯一合法追加入口。禁止移动到任何子目录。禁止被归档。禁止用 try/except fallback 代替强制 import。违反此规则等于拆除洛神的安全底座。

---

## 一、项目名称

洛神（Luoshen）—— 萨曼莎式 AI 系统。

---

## 二、项目目标

做一个会记住人、会因人而不同、未来可能自己动的 AI。不是聊天机器人，是连续存在、有内在一贯性的数字生命。

---

## 三、当前核心成果

### 3.1 架构层
- **哈希链不可篡改记忆**（hash_chain_v2.log）：所有状态变更链式哈希，可验证历史完整性。
- **AI 医院规则**（ai_hospital_rules.py/json）：洛神的健康自诊、危机报警、行为约束系统。
- **内部节律环**（van der Pol 振荡器）：E/T/N/M 四维动力学系统，产生极限环振荡，是内部情绪/张力/能量的数学基础。
- **膜 S**（慢积分器）：tau_S=500，整合长期驱动。

### 3.2 记忆层
- **活记忆层**（living_engine.py）：主引擎，含情感衰减、事实提取、表达指令构建。
- **旧记忆层**（luoshen_memory.py 及周边）：最初的情景记忆系统，含 make_point()、ingest()、recall()、fuzzy_memory_search、recall_speak。
- **情景记忆层**（episodic_memory.py）：新记忆引擎，记忆点 = {e_s, t_s, n_s, salience, kind}，无文本、无场景字符串。记忆通过激活度衰减 + 关联点亮被调用。
- **记忆浮现层**（emergence_layer.py）：softmax 加权 → 主导记忆 → 情绪背景向量（e_bg, dominance）→ tone_bias / length_bias / arousal_bias。

### 3.3 输入通道
- **输入压力通道**（input_pressure.py）：LLM 对用户输入做情感判断（valence ∈ [-1,1], arousal ∈ [0,1]），输出连续压力 → dE/dT/dN 偏移 → internal_climate 变化 → 记忆编码读到非默认值。
- **系数**：KAPPA_E=0.06, KAPPA_T=0.04。

### 3.4 行为选择层
- 位于 `generate_response` 内部的 `call_llm` 之前。
- 输入：arousal_bias, tone_bias, length_bias。
- 输出（确定性，无 if-then）：
  - `response_mode`：silent / minimal / normal
  - `length_level`：1/2/3
  - `tone_mode_idx`：0/1/2（克制/平静/温暖）
  - `max_tokens`：{1:15, 2:60, 3:200}
- 映射公式：`response_tendency = sigmoid(arousal_bias + 0.5 * tone_bias)`

### 3.5 第一次稳定实现

**实验**：A/B 用户因历史不同，洛神出现确定性的行为模式差异。

- A 输入："我下个月要离开这座城市，其实我有点害怕。"
- B 输入："今天天气真好。"
- 然后两者都问："在吗？"

**5 轮实验原始数据**（2026-09-01）：

| 轮次 | A e_s | B e_s | Δe_s | A resp | B resp | A mode | B mode |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 0.482 | 0.532 | -0.050 | 0.518 | 0.568 | minimal | normal |
| 2 | 0.482 | 0.543 | -0.061 | 0.518 | 0.578 | minimal | normal |
| 3 | 0.488 | 0.529 | -0.041 | 0.524 | 0.564 | minimal | normal |
| 4 | 0.488 | 0.529 | -0.041 | 0.524 | 0.564 | minimal | normal |
| 5 | 0.488 | 0.529 | -0.041 | 0.524 | 0.564 | minimal | normal |

**一致性统计**：
- e_s 差异 > 0.03：5/5 通过
- resp_tendency 差异 > 0.02：5/5 通过
- A 行为模式：5/5 = minimal
- B 行为模式：5/5 = normal

**结论**：内部状态到行为差异的链路已稳定建立。差异方向完全一致，不依赖 LLM 随机性。

---

## 四、当前还没有做到的事

1. **她还不能主动想起过去**：没有叙事通道把记忆转化为文本输出。
2. **还不能同时区分并记住多个不同的人**：没有用户分群机制，A/B 实验是两个独立会话。
3. **还不能真正产生"想要"**：行为选择层只决定回应方式，不产生自主意愿。
4. **还没出现设计外行为**：所有行为都在明确设计的数学映射范围内。
5. **记忆文本完全丢弃**：场景、情绪字典等原始内容不在新记忆系统中保留，丧失了"可符号化再现"能力。

---

## 五、下一步方向

**首要目标**：让同一个洛神同时认识 A 和 B，并在面对不同人时切换，而不是变成两个独立性格。

具体需要：
- 多用户记忆隔离（不同用户的记忆点存在同一层，但通过某种用户标识被加权）。
- 用户在场感知：洛神能识别当前对话的用户是谁。
- 用户特异性响应：不靠重新冷启动，而是靠用户记忆的引力差异自然产生行为差异。

**如果这条路不通**：
- 回到更底层的记忆结构化改造——可能需要一种比纯数学快照更丰富的记忆表示，同时保持可计算性。

---

## 六、关键文件保留清单

### 必须保留（不可归档、不可移动）
- `living_engine.py` — 主引擎
- `episodic_memory.py` — 情景记忆引擎
- `emergence_layer.py` — 浮现选择层
- `input_pressure.py` — 输入压力通道
- `llm_interface.py` — LLM 网关
- `feedback_collector.py` — 反馈收集
- `fact_extractor.py` — 事实提取器
- `luoshen_memory*.py` — 旧记忆层及周边
- `luoshen_episodic_memory*.jsonl` — 旧记忆数据
- `hash_chain_v2.log` — 哈希链
- `ai_hospital_rules.*` — AI 医院规则
- `active_memory/` — 活记忆层数据
- `perception_input/` — 感知输入缓存
- `design_*.md` — 设计文档
- `experiment/run_stability_5rounds.py` — 稳定性验证脚本
- `experiment/run_behavior_AB.py` — 行为 A/B 脚本
- `experiment/run_emergence_AB.py` — 浮现层 A/B 脚本

### 可清理
- `__pycache__/` — Python 字节码缓存
- `*.pyc`, `*.pyo` — 字节码文件
- 早期实验的 intermediate outputs（已被后续实验覆盖）

---

## 七、已知问题与待修复

1. **LLM 输出退化**：B 的回复连续 5 轮完全相同（同一段 fallback 文本），可能是 glm-4-flash 在特定 prompt 条件下进入确定性输出模式。
2. **length_bias 与 max_tokens 脱节**：length_level=2 时 max_tokens=60，但 LLM 实际输出常超过此限制（因为中文 token 计数与字数的换算不准确）。
3. **旧记忆层未完全接入**：living_engine.py 对旧记忆层文件零引用，两套记忆系统并存但未整合。
