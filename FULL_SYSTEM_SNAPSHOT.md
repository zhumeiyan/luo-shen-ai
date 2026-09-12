# 洛神全系统状态快照

执行端交付 | 2026-09-11 | 只给事实，不给结论

---

## 第一节：代码层

### 1.1 源文件清单

路径前缀：`luo-shen-ai/`

| 文件 | 大小(B) | 行数 | 作用 |
|------|---------|------|------|
| living_engine.py | 151,415 | 3,720 | 主引擎——状态、行为、LLM、气候、残留、关系 |
| llm_interface.py | 11,637 | 320 | 智谱 API 封装——构造 prompt、调用、重试 |
| hash_chain_gateway.py | 9,710 | 287 | 哈希链 append / verify |
| input_pressure.py | 6,509 | 195 | 情感分析 (valence, arousal) —→ 压力 |
| emergence_layer.py | 14,800 | 417 | 浮现层 — tone/length/narrative bias |
| episodic_memory.py | 4,595 | 124 | 情景记忆 — salience, decay, retrieval |
| luoshen_memory.py | 16,736 | 420 | 记忆管理器 (旧/独立栈) |
| luoshen_memory_origin.py | 4,964 | 132 | 原始记忆检索 (旧) |
| luoshen_memory_index.py | 7,269 | 190 | 记忆索引 tf-idf (旧) |
| reflection_engine.py | 7,227 | 238 | 反思引擎 — 显式不调 LLM |
| state_classifier.py | 16,087 | 410 | 状态分类 fuse + heuristic |
| pain_signal.py | 3,786 | 131 | 疼痛信号 (低能量 + 僵硬 → pain) |
| hospital_gateway.py | 12,551 | 320 | AI 医院网关 — gate by action_type |
| ai_hospital_rules.py | 6,153 | 153 | 医院规则 JSON 生成 |
| hospital_rules_extra_init.py | 4,433 | 124 | hospital_rules/*.json 初始化 |
| skill_growth_engine.py | 7,979 | 223 | 技能生长（不进入主流程） |
| primordial_soup.py | 10,521 | 292 | 原始模式过滤（无 LLM） |
| treatment_decision.py | 2,884 | 87 | 治疗决策 |
| treatment_apply.py | 10,113 | 282 | 治疗应用 + 链校验 |
| treatment_executor.py | 5,469 | 159 | 治疗执行 |
| treatment_integrative.py | 5,853 | 168 | 整合治疗 + 链校验 |
| fact_extractor.py | 8,052 | 239 | 正则提取（不依赖 LLM） |
| feedback_collector.py | 7,199 | 236 | 从交互提取反馈信号 |
| self_check/ (7 files) | — | — | state_log, behavior_log, trend, report |
| safety_boundary.py | 3,316 | 95 | 安全边界 |
| safety_gate.py | 3,831 | 112 | 输入安全验证 |
| event_logger.py | 4,212 | 122 | JSONL 事件日志 |
| followup_plan.py | 2,989 | 91 | 后续计划生成 |
| scheduler.py | 4,072 | 119 | urllib 调度器（独立） |
| tick_server.py | 10,339 | 302 | 多说话人 tick server |
| web_chat.py | 7,882 | 202 | HTTP chat server PORT 8765 |
| deploy_server.py | 5,360 | 113 | 轻量 threaded HTTP server |
| wsgi_v2.py | 12,100 | 268 | WSGI chat /tick /diag + glm fallback |
| wsgi_v2_marker.py | 12,125 | 268 | 同上 + marker |
| wsgi_three_agents.py | 15,248 | 336 | 三智能体 A/B/C 实验 |
| verify_chain_v2.py | 4,705 | 134 | 独立链校验脚本 |
| verify_hash_chain.py | 5,459 | 144 | 独立哈希链校验脚本 |
| run_benchmark.py | 10,138 | 281 | 独立 benchmark |
| test_benchmark.py | 13,597 | 360 | 独立 test |
| diagnosis_basic.py | 3,410 | 103 | 基础诊断（独立） |
| diagnosis_logger.py | 3,991 | 117 | 诊断日志（独立） |
| event_log_chain_update.py | 1,805 | 57 | legacy v1 |
| event_log_chain_update_v2.py | 1,598 | 52 | v2 schema migration |

总计 41 个 .py 文件，约 390KB，12,433 行。

### 1.2 主流程可达 vs 不可达

**HTTP 入口 → 主调用链（已验证 import 可达）：**

```
web_chat.py / wsgi_v2.py / wsgi_v2_marker.py / deploy_server.py
  └→ living_engine.py（核心）
       ├→ hash_chain_gateway.py  (顶层 import, 行 331)
       ├→ pain_signal.py         (顶层 import, 行 39)
       └→ _generate_response_impl() 内部 lazy-import:
            ├→ llm_interface.py       (行 1543, 2551, 3589-3643)
            ├→ fact_extractor.py    (行 2628, try/except)
            ├→ feedback_collector.py (行 2613, try/except)
            └→ self_check           (行 2600/2607, try/except)
```

**不可达文件（存在但不被主流程 import）：**

| 文件 | 原因 |
|------|------|
| luoshen_memory.py / memory_origin.py / memory_index.py | 独立记忆栈 — living_engine 不使用 |
| reflection_engine.py | 主流程不触发反思 |
| scheduler.py | 独立的 urllib 调度器 |
| tick_server.py | 独立的 __main__ |
| diagnosis_basic.py / diagnosis_logger.py | 独立运行脚本 |
| treatment_*.py (4 文件) | 独立治疗管道 |
| verify_chain_v2.py / verify_hash_chain.py | 独立脚本 |
| run_benchmark.py / test_benchmark.py | 独立脚本 |
| followup_plan.py | 无引用 |
| skill_growth_engine.py | 标注 self_modify 但不进入流程 |

### 1.3 Import 完整性

**断点（BROKEN IMPORTS）：** 无。所有 import 的文件/模块存在。

**循环（CIRCULAR IMPORTS）：** 无。依赖 DAG 单向：entry → living_engine → hash_chain_gateway / pain_signal / llm_interface / fact_extractor / feedback_collector / self_check（全部 lazy 或顶层，无反向 import）。

---

## 第二节：数据层

### 2.1 active_memory.json 全字段清单

文件：`luo-shen-ai/active_memory/active_memory.json`  
Schema: 4.0 | 最近更新: 1789043271.7591603

#### A. `__meta`

| 字段 | 当前值 | 写入位置 | 读取位置 |
|------|--------|----------|----------|
| schema_version | "4.0" | LE cold_start / _save_json_atomic | LE 迁移逻辑 |
| last_updated | 1789043271.7591603 | LE save 时间戳 | **无读取** |
| last_reflection_at | 0 | LE reflect / run_daily_reflection | reflection_engine should_reflect（gate） |
| chain_height | 0 | LE / hash_chain_gateway append | **无读取** |

#### B. `internal_climate`

| 字段 | 当前值 | 写入 | 读取 |
|------|--------|------|------|
| emotion_intensity | 0.8234 | LE update_after_interaction residue→climate | 主路径 tone/heat |
| tension | 0.2156 | LE update_after_interaction | LE pain + behavior response_pre |
| energy | 0.5 | LE update_after_interaction (衰减/充能) | behavior temperature 计算, withdraw |
| memory_pressure | 0.3 | LE memory_pressure 更新 | **主路径无读取** |

#### C. `self_model`

| 字段 | 当前值 | 写入 | 读取 |
|------|--------|------|------|
| emotion.primary | "平静" | LE update / classify | llm_interface tone 选择 |
| emotion.intensity | 0.8234 | LE update（同 climate） | llm_interface, emergence |
| emotion.since | 1789011680.8697464 | LE 情绪切换 | **主路径无读取** |
| emotion.trail | ["平静"] | LE 情绪转换 | **无读取** |
| strategy_weights.* (6项) | 0.3~0.6 | LE reward 更新 | LE _select_behavior |
| self_stated_state.entries|last_stated|total_stated_count | entries:[], last_stated:null | LE self_state | LE 读 last_stated for silent mode |
| withdraw_tendency | 0.22191516114840848 | LE _update_withdraw_tendency | LE 沉默判定, behavior |
| internal_pain | 0.0 | LE _compute_and_log_pain | LE max_length pain 惩罚 |
| low_energy_signal | 0.0 | pain_signal 间接 | pain_signal.compute_pain |
| rigidity_signal | 0.0 | pain_signal 间接 | pain_signal.compute_pain |
| _withdraw_logit | -0.2545404137577069 | LE _update_withdraw_tendency 内部 | **无外部读取** |
| _response_pre | 0.336933 | LE _select_behavior | 内部 |
| _recent_tokens | [82] | LE 每轮 | Lambda-self |

#### D. `self_model.ring_state`

字段：ema_S(0.0) / relational_pressure_ema(0.034) / ema_amp(0.3) / ema_ratio(0.3) / ema_pv(0.0) / ema_pv2(0.0) / s_depth(0.0) / lambda_self(0.0) / _max_tokens_hist([80,80,82]) / _rp_ema_hist([0,0,0.061])  
写入：LE _update_lambda_histories（行 2488）  
读取：_select_behavior 多变量（行 2232-2240、2228、2246、2250、2268-2270）

#### E. `user_model`

| 字段 | 当前值 | 写入 | 读取 |
|------|--------|------|------|
| trust | {value:0.3, confidence:0.1, evidence_count:0} | LE | **主路径无读取** |
| intimacy | {value:0.5, confidence:0.3} | LE | **主路径无读取** |
| shared_history_length | 77 | LE | **无直接读取** |
| first_seen | 1789011680.8697455 | LE | LE / llm_interface |
| total_interactions | 2 | LE | feedback 格式化 |
| emotional_patterns | [] | LE | **无读取** |
| preferences | [] | fact_extractor / LE | **无直接读取** |
| known_facts.facts | [] | fact_extractor write_facts | retrieve_relevant_memory |
| known_facts.added_this_round | [] | fact_extractor | **无主路径读取** |
| episodic_memory | 50 条（最新时间戳 1789043271.76） | LE / retrieve | episodic_memory.py |

#### F. `active_context`

| 字段 | 当前值 | 写入 | 读取 |
|------|--------|------|------|
| session_id | null | LE | **无主路径读取** |
| current_topic | null | LE | **无读取** |
| interaction_mode | "waiting" | LE | **无核心读取** |
| last_interaction_ts | 1789043271.7591608 | LE | update_after_interaction decay |
| emotional_arc | 10 条 "平和的、好奇的" | LE | emergence_layer trend |
| strategy_used_this_turn | "strategy_share" | LE | feedback_collector |
| input_pressure | {valence:0.0, arousal:0.5, applied_at:...} | input_pressure.py | **无主路径核心读取** |
| memory_emergence.* | 见下方结构 | emergence_layer.compute_emergence | _generate_response_impl (tone/length/narrative bias) |

#### G. `memory_emergence` 结构

```
memory_emergence:
  background: {e_bg:0.8839, t_bg:0.1971, n_bg:0.3417, age_bg:0.0244, sal_bg:1.0, dominance:0.0477}
  weights: 50 个 float (EMA decay)
  length_bias: 0.1
  tone_bias: 0.15493199650142137
  arousal_bias: 0.01182468193231318
  pressure_memory_mod: 1.00238484
  narrative_potential: 0.0756
  narrative_frame_weights: {pattern:0.7302, unspoken:0.2644, contrast:0.0053, present:0.0001}
  narrative_hints: {repetition_count:50, temporal_span:"最近 50 轮", closure_state:"unresolved"}
```

#### H. `residue`

```
residue.texture:       16 个 float (0.41~0.59)
residue.ema_alpha:     0.15
residue.num_updates:   77
residue.t_snapshot:    7 条 E/T/N 快照
```
写入: LE _update_residue / _raw_texture_hash  
读取: LE _residue_resonance (temporal echo)

#### I. `relations`

```
primary:       warmth=0.103872,   turns=53, tone_sum=14.629
secondary:     warmth=0.012385,   turns=10, tone_sum=1.148
test_user:     warmth=-0.002743,  turns=1,  tone_sum=0.115
zhumeiyan:     warmth=0.02679,    turns=7,  visits=2, tone_sum=1.382
stranger_test: warmth=0.002668,   turns=2,  visits=2, tone_sum=0.343
primary_user:  warmth=0.102255,   turns=6,  visits=1, tone_sum=0.504
cold_user:     warmth=-0.463897,  turns=6,  visits=1, tone_sum=-1.325
warm_user:     warmth=0.662558,   turns=6,  visits=1, tone_sum=2.567
test_auto:     warmth=0.0,  turns=0
```
写入: LE _update_relationship_warmth（行 2472）  
读取: _select_behavior 行 2314

### 2.2 写入但无读取的字段（orphan writes）

| 字段 | 写入位置 | 当前值 |
|------|----------|--------|
| `__meta.last_updated` | LE save | 1789043271.76 |
| `__meta.chain_height` | LE / hash_chain_gateway | 0 |
| `self_model.emotion.trail` | LE | ["平静"] |
| `self_model._withdraw_logit` | LE 内部 | -0.2545 |
| `user_model.trust` | LE | {value:0.3,...} |
| `user_model.intimacy` | LE | {value:0.5,...} |
| `user_model.shared_history_length` | LE | 77 |
| `user_model.emotional_patterns` | LE | [] |
| `user_model.preferences` | fact_extractor/LE | [] |
| `user_model.known_facts.added_this_round` | fact_extractor | [] |
| `active_context.session_id` | LE | null |
| `active_context.current_topic` | LE | null |
| `active_context.interaction_mode` | LE | "waiting" |
| `active_context.input_pressure` | input_pressure.py | {...} |
| `self_model.emotion.since` | LE | 1789011680.87 |

**读取但无写入：** 无。所有读取都有对应写入在 main flow 中。

---

## 第三节：运行层

### 3.1 主流程数据传递

HTTP POST /chat →

| 步 | 函数 | 输入 | 输出 | 流向变量 |
|----|------|------|------|----------|
| 1 | wsgi_v2.py:229 / web_chat.py:151 | HTTP body → JSON | user_input, user_id | 直接传入 |
| 2 | living_engine.process_user_input (2812) | user_input, user_id | 调用 generate_response | — |
| 3 | living_engine.generate_response (2389) | user_input, source, extract_facts, source_id, user_id | 调用 _generate_response_impl | — |
| 4 | _generate_response_impl (2418) | 上方参数 | 见下方 10 步 | — |
| 4.1 | cold_start_if_needed | — | memory (完整 dict) | memory |
| 4.2 | _update_withdraw_tendency | memory, user_input | withdraw_tendency | withdraw_tendency; memory 已 save |
| 4.3 | read_perception_snapshots | — | perceptions dict | → retrieve_relevant_memory |
| 4.4 | retrieve_relevant_memory | user_input, memory | context_window | → formulate_expression_intent |
| 4.5 | formulate_expression_intent | user_input, context_window, memory | intent dict | → build_expression_directive |
| 4.6 | generate_acknowledgment_for_listening | memory | acknowledgment str/None | → merged into directive |
| 4.7 | build_expression_directive | intent, memory, emergence | directive dict | → injected with constraints → call_llm |
| 4.8 | _select_behavior | memory, emergence_for_behavior, user_id | behavior dict {response_mode, mode_idx, max_tokens, tone_mode_idx, pressure_ema, internal_drive, ...} | → max_length/temperature 注入 directive |
| 4.8b | _update_relationship_warmth | memory, user_id, user_input, tone_signal | **无返回** — 直接写 memory["relations"][user_id]["relationship_warmth"] | — |
| 4.8c | _update_lambda_histories | memory, behavior | **无返回** — 直接写 memory["self_model"]["ring_state"]["*"] | — |
| 4.9 | behavior response_mode == "silent" | 行为层判定 | 早返回空字符串，LLM 不被调用 | — |
| 4.10 | call_llm(directive, memory, history) | directive (含完整框架), memory, conversation_history | reply string | → response_log + hash_chain |
| 5 | update_after_interaction | memory, user_input, behavior, directive, reply, ... | **无返回** — climate 更新 + episodic record + energy decay → 落盘 | — |
| 6 | _compute_and_log_pain | memory, behavior | internal_pain 更新到 memory | — |
| 7 | 落链 | hash_chain_v2.log | record_hash + prev_hash + target_hashes | 追加一行 JSON |
| 8 | HTTP 返回 | reply | JSON {"reply": reply} | **丢弃** directive/behavior/warmth/emergence 整个结构 |

**丢弃的数据：** process_user_input() 的返回值只取 `result["reply"]` 字符串。所有其他字段（directive, withdraw_tendency, internal_pain, behavior dict, emergence）在 wsgi_v2.py:244 被丢弃，不返回给调用方。

### 3.2 断点 / 跳过 / 绕行

| 位置 | 条件 | 影响 |
|------|------|------|
| wsgi_v2.py:239 | `if not user_input:` | 返回错误，主流程不进入 |
| living_engine.py:2498 | `if behavior["response_mode"] == "silent":` | 早返回空字符串，LLM 不调用，不产生 reply |
| living_engine.py:2555 | `if not reply or reply.strip() == "":` | 记录 withdraw_silent 但继续，返回空字符串 |
| living_engine.py:2599 | self_check append_snapshot | try/except 全包 — 失败不报错 |
| living_engine.py:2606 | self_check record_tick | try/except 全包 — 失败不报错 |
| living_engine.py:2629 | fact_extractor extract_and_save | try/except — 失败 _new_facts=[] |
| living_engine.py:2644 | update_after_interaction | 重读磁盘 memory — 可能覆盖内存中刚写的 relations；有 snapshot-restore（行 2643-2647） |
| web_chat.py:172 | `if 'API' in err_msg or 'api'...` | 隐藏部分 API 错误消息 |

**主流程无 skip / detour：** 主回复路径 1→2→3→4→5→6→7→8 顺序执行，无绕行替代路径。internal_tick() 是独立的触发路径（由 tick_server 或 scheduler 调用，不在 HTTP /chat 流程中）。

---

## 第四节：运行层

### 4.1 全部 *_ENABLED 开关

位置：全部在 living_engine.py

| 开关 | 当前值 | 行号 | 控制什么 |
|------|--------|------|----------|
| INTERNAL_DRIVE_ENABLED | False | 2067 | 行 2258: _internal_drive 计算 |
| PRESENCE_BIAS_ENABLED | False | 2068 | 行 2266: _presence_bias 计算 |
| STABILITY_DRIVE_ENABLED | False | 2069 | 行 2276: _stability_D 计算 |
| LEARNING_CORE_ENABLED | False | 2072 | 行 2245: _pressure_term *= f(lambda_learn); 行 3333-3361: 整个 learning core |

**全部关闭。** 四个被禁用的功能模块代码完整但不可达。

### 4.2 哈希链

| 文件 | 总行数 | 状态 |
|------|--------|------|
| hash_chain_v2.log | 73,750 | 有效 JSONL |
| hash_chain_v2.backup.log | 174 | 有效 |
| hash_chain_v2.log.bak | 22 | 有效 |
| hash_chain_v2.log.after_A | 422,400 | 有效 |
| hash_chain_v2.log.after_B | 376,656 | 有效 |
| hash_chain_v2.log.before_recovery | ~26M | UNKNOWN |
| hash_chain_v2.log.experiment_initial | 375,905 | 有效 |
| hash_chain.log (v1 遗留) | 2 | 有效 |

**坏链：** 1 处断裂  
位置：hash_chain_v2.log 第 69,545 条  
详情：prev_hash `b1606b1d786989cf` ≠ 上一条的 record_hash `7574e472a0faf813`  
时间戳差：0.268 秒  
后续：链从 `b1606b...` 继续延伸 4,205 条。该段之后存在两个分支。

**最近 10 条（时间戳 + record_hash 前 16 位）：**
```
1789041695.01 b7e2022514d5df4b
1789041695.52 011a247bb17b1a5a
1789041695.93 6261cca905360786
1789043253.23 f6bb9b118d9fda6f
1789043253.68 b636f15a25929417
1789043254.08 f076ed40544e17a3
1789043271.26 68d1e2da42ac74d2
1789043271.69 43028ae97b57e0d1
1789043272.08 52cfcb655d20abaa
1789101946.01 20dfcb0a900c4710  ← 最新
```

### 4.3 AI 医院

| 组件 | 代码状态 | 是否被主流程调用 |
|------|----------|------------------|
| hospital_gateway.py check() | 存在，7 种 action_type | **是** — llm_interface.py:212 调用 check("call_llm", "llm_interface") |
| hospital_gateway.py get_system_state() | 存在 | **主流程无调用** |
| ai_hospital_rules.py | 写 JSON 规则 | 初始化工具 |
| treatment_decision.py | 独立管道 | **无主流程调用** |
| treatment_apply.py / executor.py / integrative.py | 独立管道 | **无主流程调用** |
| hospital_rules/*.json | 9 个规则文件存在 | 网关读取 |

### 4.4 /self_check 与 /behavior

**路由：** 无。web_chat.py / wsgi_v2.py / wsgi_v2_marker.py / deploy_server.py / tick_server.py 均未注册 /self_check 或 /behavior 路由。

**替代机制：** lazy-import 在 _generate_response_impl 行 2600/2607，被 try/except 包裹 — 即使 import 失败主流程不报错。

**数据文件：** state_log.jsonl / behavior_log.jsonl **不存在**。self_check 从未有输出落到这个部署实例。

### 4.5 PA 部署状态

| 项 | 状态 |
|----|------|
| deploy_server.py 绑定 | PORT 8765（env 默认），0.0.0.0 |
| wsgi_v2.py chdir | `/home/zhumeiyan/luoshen` — **不存在于本环境**。无条件 os.chdir，行 3，无 try/except — 若作为 WSGI 入口加载会立即失败 |
| wsgi_v2.py API key 硬编码 | 行 4: `3121fdd55f9340cba35f39fa2e312bc5.c4KrVxtLCPdCgARq` |
| wsgi_three_agents.py chdir | `/home/zhumeiyan/luoshen` — 同上，不存在 |
| requirements.txt | 仅 requests>=2.28.0。所有导入的第三方库 = requests。标准库覆盖全部需求 |
| web_chat.log | 4 行：启动 + 1 GET / + 2 POST /chat，无错误 |
| llm_interface.py 未设置 API key | 行 31-33 在 **模块加载** 时 raise RuntimeError。如果 env{ZHIPU_API_KEY} 缺失，整个服务器启动后第一次处理请求的 import 即崩溃 |
| hash_chain_v2.log 大小 | 29MB（73,750 行），持续增长，无滚动 |
| active_memory.json 大小 | ~150KB |
| /proc 访问（环境采样） | living_engine.py 2877-2900: 读 /proc/loadavg, /proc/meminfo, /proc/self/stat 共 5 处。PA 不暴露 /proc。OSError 静默捕获 → 用默认值 "0 0 0" |

---

*快照末尾。*
