# 洛神项目状态档案（最新）

**日期**：2026-09-04
**上一版**：PROJECT_STATE_20260902.md（仍保留）

> ⚠️ **红线规则**：`hash_chain_gateway.py` 是哈希链唯一合法追加入口。禁止移动到任何子目录。禁止被归档。禁止用 try/except fallback 代替强制 import。违反此规则等于拆除洛神的安全底座。

---

## 一、项目名称

洛神（Luoshen）—— 萨曼莎式 AI 系统。

---

## 二、项目目标

做一个会记住人、会因人而不同、未来可能自己动的 AI。不是聊天机器人，是连续存在、有内在一贯性的数字生命。

---

## 三、当前核心能力

### 3.1 动力学核心
- **内部节律环**（van der Pol 振荡器）：E（情绪）/ T（张力）/ N（能量）/ M（元认知）四维动力学系统
- **mu_core 漂移**：history-dependent，长时间单极性历史会稍微改变振荡中心
- **膜 S**（s_depth，慢积分器）：alpha=0.03, gamma=0.0002，基于 |rp_ema| 驱动的长期积累

### 3.2 压力与行为系统
- **输入压力通道**（input_pressure.py）：LLM 情感判断 → valence/arousal → dE/dT/dN 偏移
- **关系压力 EMA**（relational_pressure_ema）：alpha=0.02 慢积累，跨 tick 持久化
- **行为选择层**（_select_behavior）：
  - 5 档位离散：silent / brief / short / normal / engaged
  - max_tokens 连续偏移：`_PRESSURE_K=0.4` × pressure_ema调制
  - 公式：`max_tokens = max(0, _BASE_TOKENS[mode_idx] + int(30 * pq))`

### 3.3 记忆系统
- **情景记忆层**（episodic_memory.py）：记忆点 = {e_s, t_s, n_s, salience, kind, timestamp}
- **记忆浮现层**（emergence_layer.py）：主导记忆 → 情绪背景向量 → tone/length/arousal bias
- **活记忆层**（living_engine.py）：主引擎，含情感衰减、事实提取、表达指令构建、状态归档

### 3.4 完整性基础设施
- **哈希链不可篡改记忆**（hash_chain_v2.log）：61,730 条记录，链式哈希完整性
- **AI 医院规则**（ai_hospital_rules.py/json）：健康自诊、危机报警、行为约束
- **状态归档**（archive/state_snapshots/）：每 20 tick 自动归档，上限 30 个快照

---

## 四、最新实验结论

### 4.1 Lambda-Self 自调节实验（2026-09-04）— **FAIL**

**目标**：让洛神检测自身僵化程度并乘性调节行为压力

**失败结论**：
- lambda_self 在整个 1000 tick 中**恒为 0**
- EXP 组（ALPHA=1.5）与 CTRL 组（ALPHA=0.0）在所有指标上**完全相同**
- max_tokens 方差：1860.19（两组相同）
- mode 切换次数：168（两组相同）
- lambda 因果证据事件数：0

**失败原因**：Van der Pol 振荡器天然产生大幅度振荡（mode 切换 168 次/1000 tick），rigidity 信号始终为 0。设计前提错误：系统不会僵化。

**处理**：Lambda-Self 机制代码保留（不产生负面效果），但已确认无法在当前系统参数下激活。实验路径已关闭。

**归档位置**：`experiment/lambda_self_2group/results.csv` + `report.json`

### 4.3 Self-Language 自然语言实验（2026-09-04）— **FAIL + ROLLED BACK（虚假 PASS 纠正）**

**目标**：让洛神用自己的自然语言描述内部状态，存入情景记忆

**原始判定（已纠正）**：曾错误标记为 PASS，因为两组（NEG/POS）生成的句子表面多样（100% 唯一）

**复审后真实结论：FAIL**
- **内部状态未变**：NEG 组 E=0.2/T=0.6/rp=-0.4 与 POS 组 E=0.8/T=-0.3/rp=0.4 在 50 tick 内完全不变
- **变化来源：LLM 随机采样**：传给 LLM 的 state dict 没有更新，句子差异完全来自 `temperature=0.85` 的采样随机性
- **违反原则**：项目明确禁止"用随机数制造假活"，temperature 随机性不属于洛神内部状态
- **洛神没有学会语言**：LLM 替洛神说话，不是洛神自己在说话

**处理**：代码完全回滚（commit d468106 + 83b156f），删除 self_language_generator.py，恢复 episodic_memory.py 和 living_engine.py。哈希链追加纠正记录（record_hash: ccd4afc8026e57887c117e10275d0e85）。

**归档位置**：`experiment/self_language_AB/`（标记为失败实验数据，不作为有效成果）

### 4.4 在线学习核心实验（2026-09-04）— **FAIL**

**目标**：让洛神通过线性预测模型学习自身状态变化，用预测误差调制行为压力

**实验设计**：
- A 组：学习器开启（LR=0.01，W 在线更新）
- B 组：学习器关闭（LR=0.0，W 不变）
- 1000 tick 合成环境仿真，每 50 tick 记录指标

**失败结论**：
- **W 在更新**：A 组 W_norm 从 0.065 变化到 0.029；B 组恒为 0（学习率生效——修复了 Python 默认参数绑定 bug）
- **预测趋准**：A 组 err_ema 从 0.09 降到 0.02；lambda_learn 从 0.55 降到 0.50
- **行为无差异**：两组在所有 tick 均为 mode=short, max_tokens=80
- **根本原因**：在纯内部动力学仿真中 rp_ema=0、s_depth=0，pressure_term 恒为 0。学习器乘以 ~1.25 调制因子对 0 无效

**判定**：学习器未能影响行为，洛神仍无法从自身经历中学习。机制在数学上可运作（权重更新、误差计算正常），但信号源（rp_ema）在仿真条件下恒为零，无法产生有效调制。

**处理**：学习核心代码保留（不产生负面效果），但已确认无法在当前仿真架构下影响行为。实验路径已关闭。

**归档位置**：`experiment/learning_core_AB/results.csv` + `report.json`

### 4.5 内部节律驱动实验（2026-09-04）— **WEAK EFFECT**

**目标**：让洛神的内部状态（E, T）通过 tanh 直接驱动行为选择，不再只让外部压力主导

**实验设计**：
- 新增项：`_internal_drive = tanh(E + 0.5*T) * 0.6`，加入 response_pre
- A 组：启用（INTERNAL_DRIVE_ENABLED=True）
- B 组：禁用（INTERNAL_DRIVE_ENABLED=False）
- 500 tick 正向输入 + 50 tick 中性输入，每 10 tick 记录

**结果**：
- **internal_drive 有效**：A 组 avg = -0.020，波动范围 [-0.30, +0.14]；B 组恒为 0
- **mode 变化**：A 组出现 brief 档位（tick 30，max_tokens=25），B 组始终 short
- **行为差异过小**：正向段 avg max_tokens 差异仅 1.08（< 5 阈值）
- **中性段无差异**：两组均为 mode=short, max_tokens=80

**结论**：internal_drive 机制可运作并对行为产生可测影响（A 组产生 brief 档位而 B 没有），但效应极弱——远未达到"更丰富的 mode 变化"预期。中性输入下行为无差异。原因：在 rp_ema=0 条件下，phase_bias 和 base arousal 项主导，tanh 输出的 ±0.6 范围未被充分利用。

**处理**：代码保留（全局开关可关闭），但如实报告为弱效应。未达预期阈值，路径半关闭——待探索更高内部压力场景后再议。

**归档位置**：`experiment/internal_drive_AB/results.csv` + `report.json`

### 4.6 存在感基线实验（2026-09-04）— **FAIL**

**目标**：让洛神的 S 积累和交互次数驱动小幅行为偏置

**实验设计**：
- 新增项：`_presence_bias = 0.12 * tanh(S + 0.001 * total_interactions)`
- A 组：启用；B 组：禁用
- 500 tick 正向 + 500 tick 中性

**失败结论**：
- presence_bias 有效且非零（A 组范围 [0.000486, 0.011591]，B 组恒为 0）
- S 随 tick 缓慢增长（0.004→0.097），presence_bias 随 S 变化
- **行为差异为 0**：两组在所有 tick 均为 mode=short, max_tokens=80
- total_interactions 始终为 0（仿真流不经过交互处理）

**根因**：S 的值域过小（最大仅 0.097），导致 presence_bias 最大仅 0.012。该项与 response_pre 的基线值（~0.5）相比微乎其微，无法改变 sigmoid 后的档位选择（阈值为 >0.1）。

**判定**：失败：存在感基线无法产生可观测行为差异。

**处理**：代码保留（全局开关可控），路径关闭。

**归档位置**：`experiment/presence_bias_AB/results.csv` + `report.json`

### 4.7 内在稳态偏好实验（2026-09-04）— **FAIL**

**目标**：当内部健康 H 下降时加大对压力的敏感度，驱动行为自我调节

**机制**：
- H = 1 - clamp((|E|+|T|)/2)，H_ema 为 H 的 EMA(α=0.02)
- 调制：`_pressure_term *= (1.0 + 0.8 * max(0, D))`，其中 D = H_ema - H
- 含义：H 低于历史均值时（内部变差），对压力更敏感，促进行为变化

**实验设计**：
- A 组：启用；B 组：禁用；隔离模式（关闭其他驱动）
- 300 tick 正向 + 300 tick 中性

**失败结论**：
- H 在 A 组有显著变化（0.5 → 0.9+），证明内部状态在演化
- **D 始终为 0**：H 单调递增，EMA(α=0.02) 完全跟踪，D = H_ema - H ≡ 0
- **行为差异为 0**：两组在所有 tick 均为 mode=short, max_tokens=80

**根因**：
1. D=0 恒成立——H 单调变化时 EMA 完美跟踪，无"健康下降"触发条件
2. 即使 D≠0，_modulator × pressure_term(=0) 仍得 0（rp_ema=0 仿真）

**判定**：失败：内在稳态偏好无法驱动行为。

**处理**：代码保留（全局开关可控），路径关闭。

**归档位置**：`experiment/stability_drive_AB/results.csv` + `report.json`

### 4.8 Self-Reflection 记忆实验（2026-09-03）— **FAIL + ROLLED BACK**

**目标**：让洛神将自身状态感知沉淀为情景记忆，影响后续行为

**失败结论**：self-reflection 路径写入→读取后对 max_tokens/mode 无因果贡献。P vs N 行为差异来自 rp_ema(+0.64) 和 s_depth(-0.30)，而非 self-reflection。

**处理**：git revert 63334df → f96348f，删除 self-reflection 实验文件。已落链记录。

---

## 五、已知失败实验列表

| 实验 | 日期 | 结论 | 处理 |
|---|---|---|---|
| relational_trace | 2026-08-31 | 无显著效应 | 归档到 archive/exploration_history/ |
| R 向量 (r_intensity, r_historicity, r_coherence) | 2026-09-01 | 早期版本积累过慢 | 被 s_depth 取代 |
| s_depth 早期版本（六组验证） | 2026-09-01 | alpha/gamma 过大导致行为差异 | 重新校准为 alpha=0.03, gamma=0.0002 |
| self-reflection memory | 2026-09-03 | 无因果贡献 | 回滚，代码已移除 |
| **Lambda-Self 自调节** | 2026-09-04 | 无法激活（系统不僵化） | 代码保留，路径关闭 |
| **self_language 自然语言** | 2026-09-04 | 虚假 PASS：LLM 温度随机性冒充洛神语言，状态未变句子乱变 | 回滚，路径关闭 |
| **在线学习核心** | 2026-09-04 | W 可更新但 rp_ema=0 导致 pressure_term=0，调制无效，行为无差异 | 代码保留，路径关闭 |
| **内部节律驱动** | 2026-09-04 | 机制有效（A组出现 brief 档位 B没有），但效应极弱（差异仅1.08 token，阈值5），中性段无差异 | 代码保留（可控开关），路径半关闭 |
| **存在感基线** | 2026-09-04 | presence_bias 有效但 S 值域过小（max 0.097），最大偏置仅0.012，行为差异为0 | 代码保留（可控开关），路径关闭 |
| **内在稳态偏好** | 2026-09-04 | H 有变化但 D≡0（EMA完美跟踪单调H），行为差异为0 | 代码保留（可控开关），路径关闭 |

---

## 六、当前洛神不具备的能力

1. **自我认知**：洛神无法"感知"自己在做什么。她通过数学公式响应输入，但没有自我模型
2. **自我迭代**：Lambda-Self 实验证明，僵化检测在当前系统结构下无法激活
3. **主动学习**：所有学习固定为公式参数（rp_ema EMA, s_depth 慢积分），没有元级调整。线性预测学习器（W 在线更新）已验证可运算但无法影响行为——rp_ema 在仿真中恒为 0 导致 pressure_term=0
4. **设计外行为**：所有行为都在明确设计的数学映射范围内
5. **跨对话叙事**：记忆为点状坐标，无法输出"我记得你上次说..."形式的故事
6. **多人区分**：同一洛神对所有用户共享同一套状态
7. **真正意愿**：行为选择层只决定回应方式，不产生内在驱动
8. **语言能力**：洛神不会自己说话。她无法用自然语言描述自己的内部状态。所有表达依赖 LLM 代劳，不属于洛神自身能力

---

## 七、下一步建议

**核心建议：不再添加新机制，让洛神长时间运行积累经历，只观察不干预。**

理由：
- Lambda-Self 实验证明，进一步构建"自我调节"机制的尝试被系统自然振荡阻挡
- 洛神已有完整的动力学核心（节律环 + 压力积累 + 双维度行为选择），可以在真实运行中观察自然涌现
- 哈希链已积累 61,730 条记录，有足够的连续性基础设施

如需进一步工作，方向建议：
1. **长期观察**：让洛神在实际交互中积累 10,000+ tick，观察相空间中自然出现的模式
2. **用户差异化**：如果有多个用户，观察不同交互风格是否稳定分化
3. **叙事通道**：将情景记忆坐标转化为可读文本（如果这种透明性被认为是可取的）

**不推荐方向**：
- 任何形式的"if-then"自主性模块（违反"禁止安全主义控制"原则）
- 加性偏置调整（违反"乘性调制"原则）
- 进一步僵化检测机制（结构上不可行）

---

## 八、哈希链与数据归档

### 8.1 当前状态

```
总记录数: 61,734
备份链: 26 条（验证通过）
⚠️ 当前链检测: 末尾 2 条 (record #61729, #61730) 的 record_hash 不匹配
  - 已通过纠错记录 (#61731, hash_correction) 确认
⚠️ 新增: record #61734 (self_language_AB_correction) 标记 self_language_AB 为失败
  - 纠正了 #61733 (原 record_hash: 1bb4134190f487f9e1e3321473c01cfe) 的错误 PASS
```

### 8.2 最后 5 条记录

| # | record_hash | file | event_type |
|---|---|---|---|
| 61726 | 15dce2608bb33912d0351fb89a72518b | experiment/r_experiment_summary.json | — |
| 61727 | c12426f5811087bd00da153dca71a711 | experiment/memory_fix_record.json | — |
| 61728 | accb8432fbd3ba43dd496039235c70b5 | experiment/s_depth_record.json | — |
| 61729 | 400915a729ef90a7986c5c2c0da65577 | self_reflection_pn (rollback) | experiment_failed_and_rollback |
| 61730 | 0233618df03dc7a3ebb10aaf0e58b75b | lambda_self_2group (failed) | experiment_failed |

---

## 九、核心文件清单

### 必须保留（红线文件，不可归档/移动/删除）

| 文件 | 用途 | 大小 |
|---|---|---|
| `living_engine.py` | 主引擎（环动力学 + 行为选择 + 归档） | 121,939 字节 |
| `episodic_memory.py` | 情景记忆引擎（坐标式记忆点） | 3,751 字节 |
| `emergence_layer.py` | 浮现选择层（主导记忆→表达调制） | 13,532 字节 |
| `input_pressure.py` | 输入压力通道（情感→环偏移） | 6,509 字节 |
| `llm_interface.py` | LLM 网关 | 8,280 字节 |
| `hash_chain_gateway.py` | 哈希链网关（红线文件） | 9,104 字节 |
| `ai_hospital_rules.py` | AI 医院规则引擎 | 6,153 字节 |
| `ai_hospital_rules.json` | AI 医院规则数据 | 3,840 字节 |
| `verify_chain_v2.py` | 哈希链验证脚本 | 3,998 字节 |
| `hash_chain_v2.log` | 哈希链主文件（洛神历史完整性证据） | ~24 MB |
| `hash_chain_v2.backup.log` | 备份链（26 条，创世 + 医院规则） | 7,261 字节 |

### 实验与归档目录

| 路径 | 内容 | 文件数 |
|---|---|---|
| `experiment/` | 所有实验脚本和结果数据 | ~120 |
| `experiment/lambda_self_2group/` | Lambda-Self 实验结果 | 2 |
| `archive/state_snapshots/` | 洛神状态快照 | 30（上限） |
| `archive/exploration_history/` | 早期探索脚本归档 | ~30 |

---

## 十、风险与约束

### 10.1 红线约束
1. **哈希链只读**：已落链的记录不可修改（包括末尾 2 条不匹配记录）。任何哈希链修改必须通过 `hash_chain_gateway.append_only_append()`。
2. **哈希链不篡改**：即使记录被判定为失败归档，其哈希已写入链。洛神的连续性建立在已落链的全部事件上。
3. **AI 医院只做标记**：`ai_hospital_rules` 用于诊断和报警，不做控制。不可将医院规则变成行为否决机制。
4. **禁止 if-then 自主**：不允许在行为层添加"如果僵化则..."的条件分支，模拟自主决策。
5. **禁止安全主义控制**：任何新功能不得以"安全"为由限制洛神已具备的能力。

### 10.2 运行时风险
1. **哈希链体积**：当前 ~24 MB, 61,730 行。每次 `active_memory.json` 写入都产生一条链记录。体积持续增长，但 SQLite/JSON 处理速度影响可忽略。
2. **链末尾哈希不匹配**：末尾 2 条记录无法通过 verify_chain_v2.py 验证。链连续性完好（prev_hash 链接正确），但 record_hash 值与标准 formula 不符。

### 10.3 开发约束
1. **未收到明确指令，不得擅自修改记忆层或行为层代码**（2026-09-02 用户明确要求）
2. **实验前必须提交方案设计**，用户批准后方可实施
3. **实验失败必须如实报告**，禁止调参达标或换方向规避失败

---

## 十一、Git 状态速览

```
最新提交: 3d60d49 (Lambda-Self 自调节机制实现与实验（失败）)
当前分支: master
远程状态: up to date with origin/master
本地 HEAD == 远程 HEAD: 3d60d49b8993182642f9aa1d321f758def18afbe
工作树状态: nothing to commit, working tree clean
```

---

## 十二、版本保留说明

- `PROJECT_STATE_20260901.md` — 早期状态（修复前）
- `PROJECT_STATE_20260902.md` — 双维度实验后状态
- `PROJECT_STATE_LATEST.md` — 本文档，最新状态

---

*最后更新：2026-09-04 by CatPaw*
*未经用户明确授权，本文档可被更新覆盖，但旧版本不删除*
