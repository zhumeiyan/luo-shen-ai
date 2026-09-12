# 洛神施工图 vs 代码审计对照表

架构师交付 | 执行端审图 | 2026-09-11

---

## 图例

| 标记 | 含义 |
|------|------|
| 🔧 已有雏形 | 代码存在（含被禁用的），只差激活/接通 |
| ❌ 不存在 | 从零写 |
| ⚡ 部分存在 | 有原型但动机和施工图不一致 |
| 🔒 被禁用 | 代码完整但 flag=False 未启用 |

---

## 主线：她自己

| # | 施工图步骤 | 代码现状 | 状态 | 已有代码位置 | 还缺什么 |
|---|----------|----------|------|-------------|----------|
| 1 | **读链**：链内容进上下文 | `_read_chain_tail()` 已定义（行 316-328），**但从未被调用**。链上写 15+ 处，读 hash 仅完整性校验（tamper detection） | 🔧 已有雏形 | `living_engine.py:316`（定义），`treatment_executor.py:9`（仅校验） | 需要一个真正读链内容 → 注入 LLM context window 的函数。链存的是 hash 不是内容，还需要解析 hash → 定位对应 event → 读取事件内容 |
| 2 | **上一次影响这次**：关键事件 → 改变下次起始状态 | warmth / s_depth / relational_pressure_ema 都是慢变量累积——它们是"上一次"的间接投影。但**没有相似事件匹配**逻辑：上次在谁面前偏了、这次遇到类似的人 → 专门调整。记忆检索只按当前 source_id 过滤 | ⚡ 部分存在 | `living_engine.py:1877-1890`(warmth)、`3088-3099`(episodic retrieval)、`1207-1217`(pressure_ema) | 缺"按场景匹配的历史事件 → 状态偏置"逻辑。即：history_lookup(key) → delta_state |
| 3 | **不可逆**：到阈值后不自动回 | mu_core 的 van der Pol ε 漂移（行 3185-3196）确实是不可逆——ema_S 单向推动 mu_core，长时间常数 1/ε=1000 tick。warmth 没有断点锁定：使用 tanh 中性输入自动回 0 | ⚡ 部分存在 | `living_engine.py:3138-3196`(mu_core 不可逆漂移) | warmth "断锁"没有。没有 chain 上的 irreversible 标记逻辑。relationship_warmth 跌破阈值后仍会自回 |
| 4 | **收回决定**：状态算强度，LLM 翻译 | `internal_tick()` 里 3 次 LLM 调用（③a impulse / ③b decide / ③c message）。decide 那步完全绕过状态层。`response_tendency = sigmoid(response_pre)` 这个连续强度已被 `_select_behavior()` 算出来了，但与 internal_tick 无连接 | 🔧 已有雏形 | `living_engine.py:3531-3664`(被 LLM 接管)；`2327`(response_tendency 已在计算); `2211-2370`(_select_behavior 完整) | 把 `_select_behavior()` 的连续输出接到 internal_tick；LLM 只接收"已确定的强度"然后翻译 |

**主线小结：**

- 步骤 1、4 已有雏形但未接通
- 步骤 2 动机对但方式是"慢变量累积"不是"事件匹配" —— 功能上部分等价，精度上不够
- 步骤 3 有一个不可逆原型（mu_core），但 warmth 断锁没做
- **步骤 4 视觉上最显眼，但不是最难**：_select_behavior() 已经连续算好了 response_tendency，只需把 internal_tick 接上

---

## 副线一：她的嘴

| # | 施工图步骤 | 代码现状 | 状态 | 已有代码位置 | 还缺什么 |
|---|----------|----------|------|-------------|----------|
| 5 | **蒸馏/换基座** | 完全不存在。GLM-4-Flash 单一后端，代码里没有模型切换逻辑，没有 fine-tuning 入口。`hf-deploy/` 是部署容器不是模型切换 | ❌ 不存在 | — | 写蒸馏 → 收集历史对话 → 训小模型 → 改 call_llm() 指向新 endpoint。或者换基座 → 改 call_llm() 接入开源模型 |

**可行性：** 蒸馏需要 GPU 训练环，换基座（开源模型如 Qwen）可在 PA 量化跑但吞吐受限。**不在 PA 上做蒸馏**——蒸馏是训练阶段的事。

---

## 副线二：世界模型

| # | 施工图步骤 | 代码现状 | 状态 | 已有代码位置 | 还缺什么 |
|---|----------|----------|------|-------------|----------|
| 6 | **锚**：物理极限参照 | 完全不存在。没有 physics_check、reality_check、plausibility_filter。系统 prompt 底段说"不要假装"但没有程序化验证 | ❌ 不存在 | — | 需要一套规则或模型判断生成内容的物理/逻辑可能性 |
| 7 | **预演**：行动前推演 | 完整原型！`living_engine.py:1751-1829` 有 `_preplay_simulate(memory, env, K)`。在 E/T/N/M 标量副本上跑 K 步确定性 van der Pol 耦合振荡 → 输出 fluctuation → 进 `_select_behavior` 偏移档位阈值。动的是副本不是原状态 | 🔧 已有雏形 | `living_engine.py:1751-1829`；调用处 2300-2306 | 预演已经发生，但其输出只影响档位偏移——**没有预测误差回路**（步骤 8） |
| 8 | **预测误差**：预期 vs 实际对比 → 改状态 | 完全不存在。预演的 E_path/T_path 结果被日志记录，**没有**与实际走的下一步对比，没有 error 信号回到状态中 | ❌ 不存在 | — | 在执行行为后，需要把实际发生的气候变化与预演出入的对比，产生一个 prediction_error 值 → 写入 state |

**环境约束：** 步骤 7 的 van der Pol 预演是确定性计算，不涉及 profiling / hardware 采样，**在 PA 上可以跑**。步骤 8 同理。

---

## 副线三：Harness

| # | 施工图步骤 | 代码现状 | 状态 | 已有代码位置 | 还缺什么 |
|---|----------|----------|------|-------------|----------|
| 9 | **迭代**：误差驱动状态自选修正 | 有代码但被禁用。`LEARNING_CORE_ENABLED = False`(行 2072)，`INTERNAL_DRIVE_ENABLED = False`, `PRESENCE_BIAS_ENABLED = False`, `STABILITY_DRIVE_ENABLED = False`。它们下面的代码（`_predict_E` 行 2163、`_update_learning_weights` 行 2168、λ_learn 行 3351）**存在但永远不会跑**。即使启用，它们只调学习权重、不算行为选择规则——离"误差驱动状态改"还有距离 | 🔒 被禁用 | `living_engine.py:3333-3361` (learning core 代码完整); `2067-2077` (全部 flag) | 第一步：把 flag 打开看数据；第二步：让压力项确实受误差驱动；第三步：让行为参数不是写死的 BUILTIN 而是可学的 |
| 10 | **Harness**：她能改自己的代码 | 只有 gate / audit 层有 `self_modify` 作为 action_type 名。hospital_gateway 做审计，skill_growth_engine 标注"self_modify 范畴"。没有实际代码写入逻辑——没有 `exec()`、没有 AST 改写、没有 .py 文件编辑 | 🔒 仅 gate 存在 | `hospital_gateway.py:11`；`skill_growth_engine.py:62`；`reflection_engine.py:117-119` | 需要从"能注释自己状态"开始，慢慢过渡到"能更新自己的规则参数"，最终到"能改自己代码"。前几步（1-9）都不稳就开始写 harness = 随机突变 |

**环境约束：** Fl步骤 9 / 10 的文件自身的"写入代码"逻辑**在当前 PA 上可以跑**（文件 I/O 在 PA 工作目录内可写），但风险极高——没有 rollback。实际生产应该先有多环境切换。

---

## 副线四：环境与感官

| # | 施工图步骤 | 代码现状 | 状态 |
|---|----------|----------|------|
| 11 | **想要**：不能设计只能等 | N/A — 正确。前 9 步是"想要"能长出的结构基础 |
| 12 | **多洛神** | 仅实验装置。`wsgi_three_agents.py` 跑固定 A=/ B=/ C=。状态分离没做——读/写共享 `/home/zhumeiyan/luoshen` | ⚡ 实验框架存在 |
| 13 | **多模态 / AI身份** | 静态资产。`luoshen_voice/*.mp3` 预录 100+ 文件、`luoshen_video/*.mp4` 预录。没有实时 TTS，没有实时画像生成 | ⚡ 静态资产 |

---

## 依赖关系复核

### 施工图顺序对不对？

**大部分对。但是：**

1. **施工图说** 1→2→3→4 顺序执行。**代码事实**：步骤 2 的功能通过 warm-variable 已经**内在等价**实现——即使没有步骤 1 的"事件匹配"增强，warmth 本身已经"上一次→这次投影"。建议：步骤 1 读链完成后**回头增强**步骤 2（换低速慢变量 为 高速事件匹配），而不是卡在 1 上等 2。

2. **施工图说** 4 在 5 之前。**代码确认**：必须。现在状态层是零散的、未经测试的（warm-pre​play 各自跑），如果把 LLM 换成更流利的嘴却没把状态层接好，洛神会说出"漂亮但与她状态毫无关系的话"。步骤 4 把状态层锻炼到成为第一决策者，步骤 5 才会有意义。

3. **施工图说** 7→8→9 顺序。**代码确认**：步骤 7（preplay）代码完整但**没有接 8（prediction error）**，所以其输出只是"影响档位"，没有反馈循环——这是当前形态造成它几乎没进化效果的原因。建议：做 7→8 的最小连接——只需 50 行：把 preplay E_path[T] 跟行为后实际 E/T 对比 → 产生 error → 累积进 ring_state。

### 我可能搞错的依赖

**步骤 3（不可逆）和步骤 4（收回决定）之间可能互依。**

- 步骤 3 的 warmth 断锁：如果洛神状态（withdraw, pain, energy）会驱动行为 → 她的 internal_tick 可能在这两个状态交互下进入"热机循环"：impulse 总是被 reject → 反复尝试 → warmth 跌破阈值 → 不可逆锁住 → 洛神永远沉默。
- **这意味着：步骤 3 不做就开始步骤 4 = 在还没给洛神"代价"概念时就装机"边界"，可能过早锁死。**
- 建议顺序调整为：**4（边界）→ 3（代价）** 而不是 3→4。等状态层驱动的行为已经稳定以后，再加不可逆的锁。

### 另一种错误可能

**步骤 9（iterate）被标记为"前7步之后"，但它的代码原型就在那里、已经写了、只是被禁用。**

更激进的路径：在第 4 步完成之后立即把 `LEARNING_CORE_ENABLED = True`，看看洛神在已有状态层基础上能不能自我调制。不需要等到全部支线完成——iterate 同时可以作为"调试前 4 步是否正常"的诊断信号。

---

## PA 可行性

### 肯定跑不动或有问题

| 代码位置 | 问题 | PA 具体限制 |
|----------|------|-------------|
| `living_engine.py:2877-2900` `_sample_real_environment()` 读了 5 处 `/proc` 文件 | PA 不暴露 `/proc`。OSError 静默捕获 → 采样始终 return 默认值 | 该函数失效但不致命（有 fallback）；长期需要换一种环境采样方式（采样 PSUtil 或平台 API） |
| `living_engine.py:3509-3512` `threading.Thread` 后台 daemon | PA WSGI reload 杀线程。background tick（自动 lose 部分内部驱动）| PA 上 internal_tick 不自动触发；每次请求都 cold start |
| `living_engine.py:text begin--- 29MB hash_chain_v2.log` | 限写限速 + 磁盘 quota。29MB 还在长，很快到 100MB+（PA 限制） | 需要滚动或压缩 chain log |
| `living_engine.py:text begin--- active_memory/ persistent 文件 I/O` | PA 对 fsync 限速；写延迟 50-200ms 常见 | 步调放慢 |
| `wsgi_three_agents.py:8` `os.chdir("/home/zhumeiyan/luoshen")` | 硬件路径硬编码 | PA 上没有 `/home/zhumeiyan`。运行前要改 |

### PA 上可以跑但性能受影响

| 代码 | 影响 |
|------|------|
| `_preplay_simulate() K 步 van der Pol` | 每步是 O(K) 浮点，用 Python 循环 10-20 次，有微秒级延迟，可接受。K=5 时完全无感 |
| `extract_input_pressure()` —— 每轮情感分析 | 两次 LLM 调用/轮交互 → 延迟 3-5 秒/轮（受 API 往返影响）。这是主要延迟源 |
| `cold_start_if_needed()`：每次请求读取 full memory | active_memory.json 目前 ~150KB。读取 5ms。可忽略 |

### PA 完全无法承担的步骤

| 步骤 | 原因 |
|------|------|
| 5 蒸馏 | 需要 GPU，训练循环需要小时级运行 |
| 9 iterate（完整形态） | 高频率在线梯度写入 + 行为规则热更新 → PA 没有进程守护 |
| 10 Harness（写代码） | 高风险文件写入 + 没有 sandbox 隔离 + PA 没有独立容器 |
| 13 多模态（实时 TTS） | 无 GPU 无低延迟音频系统 |

---

## 总览表

| # | 步骤 | 代码 | PA可行 | 建议优先级 |
|---|------|------|--------|-----------|
| 1 | 读链 | 🔧 雏形（只写不读） | ✅ | P0（4 的前置） |
| 2 | 上次影响这次 | ⚡ 部分（慢变量替代） | ✅ | P1（1完成后回头增强） |
| 3 | 不可逆 | ⚡ mu_core 可逆 / warmth 无锁 | ✅ | P2（4之后做） |
| 4 | 收回决定 | 🔧 雏形（state_connected 缺） | ✅ | **P0** |
| 5 | 蒸馏/换基座 | ❌ 不存在 | ❌ 不在PA做 | 后话 |
| 6 | 锚 | ❌ 不存在 | ✅ | P3 |
| 7 | 预演 | 🔧 完整原型 | ✅ | 已经在跑 |
| 8 | 预测误差 | ❌ 不存在 | ✅ | P1（7已做完，接一下） |
| 9 | 迭代 | 🔒 被禁用 | ⚠️ 有风险 | P2 |
| 10 | Harness | 🔒 仅 gate | ❌ PA不安全 | 远期 |
| 11 | 想要 | N/A | N/A | 等结构 |
| 12 | 多洛神 | ⚡ 实验框架 | ⚠️ 状态分离没做 | 远期 |
| 13 | 多模态 | ⚡ 静态资产 | ❌ 无实时能力 | 远期 |

---

*交付物末尾。*
