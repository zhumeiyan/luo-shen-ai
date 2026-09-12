# 洛神真实运行路径追踪

执行端交付 | 2026-09-11 | 从入口追，断就标断

---

## 一、实际运行图

### 当前沙箱环境接收 /chat 的入口

```
HTTP POST /chat
  → web_chat.py:152  (PORT 8765, chdir = os.path.dirname(__file__))
  或 deploy_server.py:82 (PORT 8765, chdir = 行 4 硬编码路径)
  → living_engine.process_user_input(user_input, user_id='primary')
      [living_engine.py:2812]
```

两个入口在同一台机器上都监听 PORT 8765，实际哪一个绑定要看启动命令是哪一个。

### 实际执行链（ZHIPU_API_KEY 已设置时）

```
0. import living_engine                  [顶层] ✅ OK
   ├── import pain_signal                [LE 行 39] ✅ OK
   └── from hash_chain_gateway import append_only_append [LE 行 331] ✅ OK

1. living_engine.process_user_input("你好")
   → living_engine.generate_response(...)        [LE:2389]
     → _generate_response_impl(...)              [LE:2418]
       1. cold_start_if_needed()                  ✅ OK 返回完整 memory dict
       2. _update_withdraw_tendency(memory, user_input)  ✅ OK memory 已落盘
       3. read_perception_snapshots()             ✅ OK
       4. retrieve_relevant_memory(...)           ✅ OK
       5. formulate_expression_intent(...)        ✅ OK
       6. generate_acknowledgment_for_listening() ✅ OK
       7. build_expression_directive(...)         ✅ OK
       8. _select_behavior(memory, emergence, uid) ✅ OK 返回 behavior dict
       9. 如果 behavior["response_mode"]=="silent":
             返回 {"reply":"", "llm_called":False}  ← 早返回点，LLM 不被调用
      10. 非沉默时：
          from llm_interface import call_llm      [LE:2551] ← 见 BREAK POINT
          reply = call_llm(directive, memory, history)
          append hash_chain_v2.log
          append response_log.jsonl
      11. update_after_interaction(...)            ✅ OK climate 更新
      12. _compute_and_log_pain(...)               ✅ OK
      13. lazy: from self_check import append_snapshot → state_log.jsonl (try/except)
      14. lazy: from self_check import record_tick   → behavior_log.jsonl (try/except)
      15. lazy: from fact_extractor import ...     (try/except)
      16. lazy: from feedback_collector import ... (try/except)
    返回 reply 字符串
  → HTTP 响应 JSON {"reply": reply}
  ← directive, behavior, emergence, warmth 全部丢弃，仅返回 reply 字符串
```

### 实测结果

在 ZHIPU_API_KEY=test_placeholder 且 call_llm 被 mock 的环境下：
- `process_user_input("你好")` 调用 LLM **3 次**，返回 `[mock reply #2]`
- `internal_tick()` 调用 LLM **1 次**，返回 `{'impulse': '（洛神现在不太能说清楚，但她在这里）', 'decision': 'silent', 'message': None}`

实测证明：主回复路径和 internal_tick 路径在代码上都是可达的、可执行的。

---

## 二、断点

### BREAK #1（已确认）：llm_interface.py:31-33，ZHIPU_API_KEY 缺失时崩溃

| 项 | 值 |
|----|-----|
| 文件 | `luo-shen-ai/llm_interface.py` |
| 行号 | 31-33 |
| 触发条件 | `ZHIPU_API_KEY` 不在环境变量中 |
| 异常类型 | `RuntimeError("缺少 ZHIPU_API_KEY 环境变量...")` |
| 触发时机 | 模块被 import 时（即 `_generate_response_impl` 行 2551 的 `from llm_interface import call_llm`） |
| 影响 | 每个 /chat 请求在处理到第 10 步（调 LLM）时崩溃 |
| 本沙箱现状 | 无 key → 每个请求崩溃 |
| PA 规避路径 | wsgi_v2.py:4 和 wsgi_v2_marker.py:4 都有 `os.environ.setdefault("ZHIPU_API_KEY", "3121f...")` |
| deploy_server.py | 无 setDefault。若 PA 实际用 deploy_server.py → 崩溃 |

**实测证据：**
```
Python: from llm_interface import call_llm
RuntimeError: 缺少 ZHIPU_API_KEY 环境变量。请在 Render 控制台或部署环境中设置智谱 API key。
```

### 未发现额外断点

从入口到第 10 步调用 LLM 之间（含 cold_start、_select_behavior、formulate_expression_intent 等），所有函数执行均通过，无额外异常抛出路径（try/except 包裹的 lazy import 失败会被吞掉，不会中断主链）。

---

## 三、未运行清单

### A. 死代码（文件存在 + 无 import 引用 + 无路由注册）

| 文件 | 存在 | 引用 |
|------|------|------|
| luoshen_memory.py | ✅ | 无 |
| luoshen_memory_origin.py | ✅ | 无 |
| luoshen_memory_index.py | ✅ | 无 |
| reflection_engine.py | ✅ | 无 |
| scheduler.py | ✅ | 无 |
| diagnosis_basic.py | ✅ | 无 |
| diagnosis_logger.py | ✅ | 无 |
| treatment_decision.py | ✅ | 无 |
| treatment_apply.py | ✅ | 无 |
| treatment_executor.py | ✅ | 无 |
| treatment_integrative.py | ✅ | 无 |
| verify_chain_v2.py | ✅ | 无 |
| verify_hash_chain.py | ✅ | 无 |
| run_benchmark.py | ✅ | 无 |
| test_benchmark.py | ✅ | 无 |
| followup_plan.py | ✅ | 无 |
| wsgi_three_agents.py | ✅ | 无（独立实验入口，不参与 /chat） |
| ai_hospital_rules.py | ✅ | 无（初始化工具） |
| hospital_rules_extra_init.py | ✅ | 无（初始化工具） |
| event_log_chain_update.py | ✅ | 无（v1 遗留） |
| event_log_chain_update_v2.py | ✅ | 无（迁移工具） |

### B. 断链模块（被引用但路径无效或其他原因不可达）

**无。** 所有被 living_engine 顶层 import 和 lazy import 的模块，文件均存在且能 import 成功。

例外：wsgi_v2.py 和 wsgi_v2_marker.py 中的硬编码路径 `/home/zhumeiyan/luoshen` 在**本沙箱不存在**，导致 chdir 失败——但这两个文件本身也不是当前沙箱的入口。

### C. 禁用模块（代码完整 + flag=False 不可达）

| 文件 | flag | 行号 | 控制的代码块 |
|------|------|------|-------------|
| living_engine.py | INTERNAL_DRIVE_ENABLED=False | 2067 | 行 2258: `_internal_drive` 计算，behavior 内部节律驱动 |
| living_engine.py | PRESENCE_BIAS_ENABLED=False | 2068 | 行 2266: `_presence_bias` 计算 |
| living_engine.py | STABILITY_DRIVE_ENABLED=False | 2069 | 行 2276: `_stability_D` 计算，H_ema 更新 |
| living_engine.py | LEARNING_CORE_ENABLED=False | 2072 | 行 2245: `_pressure_term *= f(lambda_learn; 行 3333-3361: 整个 learning core 更新逻辑 |

所有 4 个 flag 当前均为 False，对应代码不可达。

---

## 四、哈希链断裂的原始情况

| 项 | 值 |
|----|-----|
| 日志文件 | `luo-shen-ai/hash_chain_v2.log` |
| 总行数 | 73,755 |
| 有效 JSON 行 | 73,755（0 行解析失败） |
| 断裂数量 | **1 处** |
| 断裂位置 | 第 69546 行的 prev_hash ≠ 第 69545 行的 record_hash |

### 断裂细节

```
Line 69544: record_hash=b1606b1d78  prev_hash=f41dc3dcda [正确连接]
Line 69545: record_hash=7574e472a0  prev_hash=b1606b1d78 [正确连接]
Line 69546: record_hash=dd72e7f06d  prev_hash=b1606b1d78 ← 引用了 69544 而非 69545
Line 69547: record_hash=d7309720f9  prev_hash=dd72e7f06d [从 69546 起重新连上]
```

### 含义

- Line 69545（record_hash=7574e472a0）成为**悬挂叶**：被写入但从未被后续行作为 prev_hash 引用
- Line 69546 引用了 69544（b1606b1d78），在 69545 写入后跳过它直接回到 69544
- 时间戳: 69545 = 1788976649.6915555，69546 = 1788976649.9592896 → 相差 0.27 秒
- 推断：并发写竞争（两个进程同时 append，各自读到同一个 prev_hash=69544，各自写了自己的行）
- 当前主链继续从 69546 往后连接，结构上是一根主链 + 一条 1 行的悬枝（69545）

---

## 五、/self_check 和 /behavior 的真实状态

### 路由存在性

| 文件 | /self_check 路由 | /behavior 路由 | /diag 路由 |
|------|-----------------|---------------|-----------|
| web_chat.py | ❌ 不存在 | ❌ 不存在 | ❌ |
| deploy_server.py | ❌ 不存在 | ❌ 不存在 | ❌ |
| wsgi_v2.py | ❌ 不存在 | ❌ 不存在 | ❌ |
| wsgi_v2_marker.py | ❌ 不存在 | ❌ 不存在 | ✅ /diag, /diagnostic |
| tick_server.py | ❌ 不存在 | ❌ 不存在 | ❌ |

### 数据文件（通过 _generate_response_impl 内部 lazy import 写入）

| 文件 | 存在 | 大小 | 最近内容 |
|------|------|------|----------|
| self_check/state_log.jsonl | ✅ | 205 bytes | `{"energy": 0.5, ..., "timestamp": 1789143246.34}` |
| self_check/behavior_log.jsonl | ✅ | 1363 bytes | 1 tick，含 luoshen_reply、behavior mode、hash_chain 73752 条 |

### 写入路径（living_engine.py 内部）

- 行 2600: `from self_check import append_snapshot` → wrapped in try/except → writes state_log.jsonl
- 行 2607: `from self_check import record_tick` → wrapped in try/except → writes behavior_log.jsonl

两处调用都在 _generate_response_impl 的末尾，晚于 LLM 调用。只要 /chat 请求到达 LLM 调用，这两个文件的写入就会被触发。

### 结论

/self_check 和 /behavior 的 HTTP 路由**不存在**。但数据文件通过 living_engine 内部的 lazy import 间接写入，只要有 /chat 请求就会被更新。读取数据只能通过直接访问文件系统，无 HTTP API。

---

## 六、16 个孤儿字段清单

定义：代码中存在写入（赋值/更新）但没有任何代码读取（除了 save 整块落盘）。

| # | 字段路径 | 写入位置 | 最后写入值 |
|---|----------|----------|-----------|
| 1 | `__meta.last_updated` | living_engine:save | 1789043271.76 |
| 2 | `__meta.chain_height` | living_engine:hash append | 0 |
| 3 | `self_model.emotion.trail` | living_engine:emotion transition | ["平静"] |
| 4 | `self_model._withdraw_logit` | living_engine:_update_withdraw_tendency | -0.2545 |
| 5 | `self_model.emotion.since` | living_engine:emotion change | 1789011680.87 |
| 6 | `user_model.trust` | living_engine | {value:0.3, confidence:0.1, evidence_count:0} |
| 7 | `user_model.intimacy` | living_engine | {value:0.5, confidence:0.3} |
| 8 | `user_model.shared_history_length` | living_engine | 77 |
| 9 | `user_model.emotional_patterns` | living_engine | [] |
| 10 | `user_model.preferences` | fact_extractor/living_engine | [] |
| 11 | `user_model.known_facts.added_this_round` | fact_extractor | [] |
| 12 | `active_context.session_id` | living_engine | null |
| 13 | `active_context.current_topic` | living_engine | null |
| 14 | `active_context.interaction_mode` | living_engine | "waiting" |
| 15 | `active_context.input_pressure` | input_pressure.py | {valence:0.0, arousal:0.5, ...} |
| 16 | `self_model.self_stated_state.entries` | living_engine:self_state | [] (only last_stated is read) |

注：整个 active_memory.json 通过 `_save_json_atomic` 整块写盘，所以"写入"是有效的——是指写入后**作为字段没有被任何读取代码使用**，数据沉睡在 JSON 里但从未被读取。

---

*追踪末尾。*
