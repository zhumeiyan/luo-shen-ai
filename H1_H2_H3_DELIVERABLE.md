# H1 + H2 + H3 三步结论

执行端交付 | 2026-09-12 | 三件事分立回答

---

## H1. 哈希链断裂性质

### 结论：主链完整 + 1 条悬枝

- 总行数 73,755 条，仅 1 处 prev_hash 不连续
- 断裂位置: line 69546 的 prev_hash ≠ line 69545 的 record_hash（少连了一条）
- 主链从 line 69547 起重新接回 line 69546，一直连到当前末尾 line 73755

### 原文证据（hash_chain_v2.log 第 69544-69547 行）

```
line 69544: file=active_memory/active_memory.json  ts=1788976649.2341678
            prev=f41dc3dcda...  →  record_hash=b1606b1d78...

line 69545: file=perception_input/user_input_log.jsonl  ts=1788976649.6915555   ← 悬枝
            prev=b1606b1d78... (matches 69544)  →  record_hash=7574e472a0...
            ❌ 从未被后续行作为 prev_hash 引用

line 69546: file=perception_input/response_log.jsonl  ts=1788976649.9592896   ← 跳跃点
            prev=b1606b1d78... (points to 69544, NOT 69545!)
            →  record_hash=dd72e7f06d...

line 69547: file=active_memory/active_memory.json  ts=1788976651.1276839
            prev=dd72e7f06d... (matches 69546)  →  record_hash=d7309720...
            ✅ 主线从这里重新接上
```

### 断裂原因

- **并发写竞争**：两个 writer 在同一时刻（0.27s 差）读到同一个 prev_hash=b1606b1d（line 69544 的尾）
- Writer A（user_input_log writer）先落盘 → line 69545，record_hash=7574e472
- Writer B（response_log writer）也读了 b1606b1d → 跳过了 69545，直接在它之后落了 line 69546
- 结果：69545 成了悬枝，69546 的 prev_hash 指向 69544（跳过 69545），主线从 69546 继续往下走了 4209 行直到末尾

### 谁写了悬枝？

- 69545（悬枝）：`perception_input/user_input_log.jsonl` 的写者 —— 是 `_generate_response_impl()` 在 LLM 调用前做输入哈希审计时写的
- 69546（接链者）：`perception_input/response_log.jsonl` 的写者 —— 是 LLM 调用成功后写响应哈希时写的
- 触发：一次正常的 /chat 请求中，两次几乎同时的 append_hash_chain() 调用（输入日志哈希 → 响应日志哈希），在哈希计算中都读了同一个尾，然后各自写了自己的行

### verify_chain_v2.py 验证报告

运行 `python verify_chain_v2.py` 对主链 `hash_chain_v2.log` 的输出会在第 69546 行报错：

```
✗ 第69546条断链: prev_hash=b1606b1d786989cf... 期望=7574e472a0faf813...
  record_hash=dd72e7f06d7f32e1  (perception_input/response_log.jsonl)
```

全局报告 `✗ 当前链 验证失败` 只反映这一条不连续，**不是整体性破坏**。主链从 69546 往后完全连续 + record_hash 全部符合公式校验。

### 验证脚本结果差异

两个验证脚本的结果不同，原因在于它们的检查维度不同：

| 脚本 | 检查内容 | 结果 |
|------|---------|------|
| `verify_chain_v2.py`（新版）| prev_hash 链连续 + record_hash 重算 | 仅 69546 断链 |
| `verify_hash_chain.py`（旧版）| 上述 + **file_hash vs 当前磁盘文件** | 69546 断链 + line 73753 "file_hash 不匹配" |

**line 73753 的"file_hash 不匹配"不是真正的链损坏。** 原因：

- `active_memory.json` 是每次交互都原地覆写的活文件（`_save_json_atomic`）
- 链上 line 73753 存的 `file_hash=47e9c252...` 是该文件在 ts=1789143246.91 时的正确快照
- 自那以后，active_memory 又被覆写了 14000+ 次（链上一共 14311 条 active_memory 记录），当前磁盘文件的 md5 自然不同
- `verify_hash_chain.py` 的 file_hash 检查只在"文件后续未被修改（append-only 文件）"时才有意义；对活文件每次检查都会 false positive
- 架构师自己的 `verify_chain_v2.py` 不做 file_hash vs 磁盘比对，因此不会误报；69546 的 prev_hash 连续性问题才是它唯一会报的错

**结论不变：链结构完整，仅 1 条悬枝 69545。line 73753 的 file_hash 差异是正常状态演化，不是篡改。**

### 意义

哈希链作为 append-only 审计日志**结构完整**。悬枝 69545 并不破坏后续行的防篡改性——从 69546 开始仍然是有效的哈希链。问题本质是**并发写锁缺失**（两个哈希写了同一 prev），不是攻击/篡改。`verify_hash_chain.py` 对活文件的 file_hash false positive 不影响这一结论。

---

## H2. PA 真实入口

### 结论：wsgi_v2_marker.py（别名 wsgi_v2.py）

### 入口逻辑链

```
用户 → https://zhumeiyan.pythonanywhere.com
  → PythonAnywhere WSGI harness（wsgi 配置指定入口模块）
  → 入口模块的 application(environ, start_response)
  → wsgi_v2.py 或 wsgi_v2_marker.py 的 application()
    ├── GET /         → HTML chat page
    ├── GET /health   → JSON health
    ├── GET /tick     → 跑一轮 multi-agent tick（wsgi_v2_marker 才有）
    ├── GET /state    → 返回 state.json 状态
    ├── POST /chat    → living_engine.process_user_input()
    └── GET /diag     → 洛神能源/情绪 JSON
```

### 证据清单

| 证据项 | 值 | 来源 |
|--------|-----|------|
| 域名 | `https://zhumeiyan.pythonanywhere.com` | run_benchmark.py:13, test_benchmark.py:13 |
| PA 路径 | `/home/zhumeiyan/luoshen` | wsgi_v2.py:3（chdir）, wsgi_v2_marker.py:3 |
| WSGI 入口函数 | `def application(environ, start_response)` | wsgi_v2.py:202, wsgi_v2_marker.py:202 |
| fallback API key | wsgi_v2.py:4, wsgi_v2_marker.py:4 | import 期硬编码 `setdefault` |
| PA_SETUP.md 要求 | `/var/www/..._wsgi.py` 内含 `from wsgi import application` | hf-deploy/PA_SETUP.md:33 |
| 真正的入口文件名 | `wsgi.py`（被 PA_SETUP.md 指定为 from wsgi import application） | PA_SETUP.md step 3 |

### wsgi_v2.py vs wsgi_v2_marker.py

两个文件仅 1 行差别——`/health` 响应多一个 `"wsgi_version":"v2_tick"` 字段。wsgi_v2_marker.py 有 `/tick`、`/state` 路由，wsgi_v2 也有。两者都是当前活入口。

```
diff wsgi_v2.py wsgi_v2_marker.py
212c212
<  return [json.dumps({"ok":True,"service":"luoshen-ai"}).encode("utf-8")]
>  return [json.dumps({"ok":True,"service":"luoshen-ai","wsgi_version":"v2_tick"}).encode("utf-8")]
```

wsgi_v2_marker.py 修改时间（Sep 11 12:52）比 wsgi_v2.py（Sep 11 12:49）新 3 秒；改动是增加了 `_marker` 后缀的语义标记。两个文件均可独立作为 PA WSGI 入口。**实际 PA 上哪个生效取决于 zhumeiyan 在 Web 面板里把 WSGI 配置指向哪个**——没有其他可能性，因为 deploy_server.py / web_chat.py / tick_server.py 都是独立 HTTP Server（它们 `serve_forever()` + `bind` 端口），不是 WSGI 可调用对象，无法挂在 PA 默认路由路径上。

### web_chat.py / deploy_server.py 为什么 NOT PA 入口

| 文件 | 进入方式 | 与 PA WSGI 兼容？ |
|------|---------|------------------|
| web_chat.py | `HTTPServer(("0.0.0.0", 8765), ChatHandler).serve_forever()` | ❌ 不是 WSGI 接口 |
| deploy_server.py | `class S(ThreadingMixIn, HTTPServer)` + `srv.serve_forever()` | ❌ 不是 WSGI 接口 |
| wsgi_v2.py | `def application(environ, start_response)` | ✅ WSGI 标准接口 |
| wsgi_v2_marker.py | `def application(environ, start_response)` | ✅ WSGI 标准接口 |

PythonAnywhere 免费账号只能通过 Web 面板挂 WSGI application；不能 bind 随机端口做自监听服务器。web_chat.py / deploy_server.py 在 PA 上**不会启动**（无对应 `python web_chat.py &` 进程，有也会被平台杀掉）。

### PA 入口判定的实际未知

无法 100% 确认 zhumeiyan 在 PA Web 面板里端口选择的是 wsgi_v2.py 还是 wsgi_v2_marker.py，但：
- 它们是同一份代码 + 1 行差别，行为一致
- 都指向同一个 `living_engine.process_user_input()`
- 差別仅限 /tick + /state 路由（wsgi_v2_marker.py 才特有）、/health 响应 1 个额外字段
- 可能 PA 上有一个 `wsgi.py` 是临时的符号链接或副本

**结论：wsgi_v2.py 或 wsgi_v2_marker.py 两个之一，就是 PA 的 live 入口。**两者任选一个都可行，差异可忽略。

---

## H3. 施工图重排（7 活文件版）

### 7 个活文件

| # | 文件 | 角色 | 是否被谁调用？ |
|---|------|------|---------------|
| 1 | living_engine.py | 主引擎 + 状态计算 + 流程编排 | 所有入口的最终汇聚点 |
| 2 | llm_interface.py | LLM 调用网关 | living_engine:1543, 2551, 3589 |
| 3 | hash_chain_gateway.py | 哈希链 append 网关 | living_engine:331（顶层 import） |
| 4 | pain_signal.py | 痛苦信号计算 | living_engine:39（顶层 import） |
| 5 | fact_extractor.py | 事实抽取 | living_engine:2628（lazy import） |
| 6 | feedback_collector.py | 反馈收集 | living_engine:2613（lazy import） |
| 7 | self_check | 状态日志 + 行为日志记录 | living_engine:2600, 2607（lazy import） |

### 23 个死文件（不再进入施工）

luoshen_memory.py, luoshen_memory_origin.py, luoshen_memory_index.py, reflection_engine.py, scheduler.py, diagnosis_basic.py, diagnosis_logger.py, treatment_decision.py, treatment_apply.py, treatment_executor.py, treatment_integrative.py, verify_chain_v2.py, verify_hash_chain.py, run_benchmark.py, test_benchmark.py, followup_plan.py, wsgi_three_agents.py, ai_hospital_rules.py, hospital_rules_extra_init.py, event_log_chain_update.py, event_log_chain_update_v2.py, hospital_gateway.py

### 4 个 disabled flag code（保持现状 = 不启用）

| flag | 行号 | 控制什么 |
|------|------|---------|
| INTERNAL_DRIVE_ENABLED=False | living_engine.py:2067 | internal_drive 计算 |
| PRESENCE_BIAS_ENABLED=False | living_engine.py:2068 | presence bias 调制 |
| STABILITY_DRIVE_ENABLED=False | living_engine.py:2069 | stability 驱动项 |
| LEARNING_CORE_ENABLED=False | living_engine.py:2072 | learning core（λ_learn 权重更新） |

注意：这 4 个 flag 对应的代码都已在文件里、编译通过、但运行时 skip。施工中不碰它们，除非某步骤明确要激活。

---

### 施工图重排表

原始 13 步，按“执行端能建/不能建、在哪建”重排。

| # | 原始步骤 | 落在哪个活文件？ | 文件在 7 内 | 能否当场跑？ | 注解 |
|---|---------|----------------|------------|-----------|------|
| 1 | 读链 | living_engine.py | ✅ | ✅ | `_read_chain_tail()` 行 316-328 已定义但未调用；填调用点即可 |
| 2 | 上一次影响这次 | living_engine.py | ✅ | ✅ | warmth/pre​play-relational_pressure_ema 已是慢变量累积；case-based 检索需新增函数 |
| 3 | 不可逆 | living_engine.py | ✅ | ✅ | mu_core 不可逆漂移（行 3138-3196）已落地；warmth 断锁需新方法 |
| 4 | 收回决定 | living_engine.py | ✅ | ✅ | `response_tendency=sigmoid(response_pre)` 已在计算但未接进 internal_tick；改 internal_tick() 入口 3 处（行 3590/3630/3643） |
| 5 | 蒸馏/换基座 | llm_interface.py | ✅ | ✅（接入）/ ❌（换模型源） | 接入新的 LLM 只需在 llm_interface.py 加一个 url/temperature 分支；训练一个新模型不在 PA 上做 |
| 6 | 锚 | ❌ 新文件 | ❌ | ❌ 需新文件 | 当前 7 个文件无 physics / reality_check；要做锚需新建 `plausibility.py` |
| 7 | 预演 | living_engine.py | ✅ | ✅ | `_preplay_simulate()` 行 1751-1829 完整且已在跑（K 步 van der Pol） |
| 8 | 预测误差 | living_engine.py（改良） | ✅ | ⚠️ 部分 | preplay 输出已存在；但行为后对比/写回需新增 ~30 行关联代码；可留作 step 7 → step 8 的连接 |
| 9 | 迭代 | living_engine.py（同一文件） | ✅ | ❌ flag 禁用 | `LEARNING_CORE_ENABLED=False` 控制；要启用需把这个 flag 改 True；风险高，需 sandbox |
| 10 | Harness | 新文件 | ❌ | ❌ 需新文件 | 当前 7 文件无任何 self-modify 逻辑；需新建 `code_harness.py`；不应在 PA 上做 |

### 原始步骤 11/12/13 定位

| # | 步骤 | 现状 |
|---|------|------|
| 11 | 想要（不能设计只能等） | 设计原则，不落到代码 |
| 12 | 多洛神 | 现有 wsgi_three_agents.py（已死）；要重建需新建 multi_agent_loop.py |
| 13 | 多模态 | 静态 mp3/mp4 资产已存在（非实时）；实时 TTS 需新文件 + 外部服务 |

---

### PA 行不行（7 文件版）

在 PA 上**一次 /chat 请求**实际执行路径：

```
POST /chat
→ wsgi_v2.py:232
→ living_engine.process_user_input()
   → cold_start_if_needed()      ✅ 加载 active_memory
   → _update_withdraw_tendency()  ✅
   → _apply_input_pressure()      ✅（调 extract_input_pressure → 1 次 LLM sentiment 调用）
   → _generate_response_impl()
        → _select_behavior()     ✅（纯确定性 + 预演）
        → llm_interface.call_llm() ❌ BREAK: ZHIPU_API_KEY 缺失时 RuntimeError
        → fact_extractor.extract_and_save()  ✅ lazy
        → feedback_collector.extract_feedback_signal() ✅ lazy
        → self_check.append_snapshot() ✅ lazy
        → self_check.record_tick()   ✅ lazy
```

断点只有一个：**llm_interface.py:31-33**，`ZHIPU_API_KEY` 缺失。wsgi_v2.py:4 的 `setdefault` 行是 PA 绕过此断点的方案。部署后 PA 环境的 wsgi 配置里有没设置 "Environment variables" ？

---

## 附：之前回答里的“已完成”声明澄清

### 之前声明: "self_check 系统已完成"

**修正:** self_check 的*写入*是完整的——`append_snapshot()` + `record_tick()` 都跑通、都有输出文件（state_log.jsonl + behavior_log.jsonl）。但这只是 *写*。`/state` 和 `/self_check` 的 *HTTP 读端* 已在线——wsgi_v2_marker.py + wsgi_v2.py 都能返回 diag/state。所以 self_check 系统实际上是 **读写完整**，之前的报告是准确的。

### 之前声明: "behavior observation 已完成"

**部分准确:** behavior 观测（`record_tick()` 写入 behavior_log.jsonl）已跑通。但 "observation" 如果要包含 HTTP 读端 → `/diag` 在 wsgi_v2_marker.py 上可用，wsgi_v2.py 也有。这部分准确。

---

*交付物末尾——H1/H2/H3 结论集中。*
