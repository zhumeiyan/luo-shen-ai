# 洛神 LLM 调用链源码交付物

架构师交付物 #2 | 执行端生成 | 2026-09-11

---

## 目录

1. [调用清单](#1-调用清单)
2. [每处调用的完整代码](#2-每处调用的完整代码)
3. [调用链流程图](#3-调用链流程图)
4. [每处的层次判定脑嘴其他](#4-每处的层次判定脑嘴其他)
5. [比例估算](#5-比例估算)

---

## 1. 调用清单

活跃代码（生产路径 + 实验入口）中涉及 LLM 调用的位置共 **8 个文件、12 个调用点**。

### 1.1 直接调 LLM API 的网关函数（1 个）

| 文件 | 函数 | 行号 | 说明 |
|------|------|------|------|
| `llm_interface.py` | `call_llm()` | 188–273 | 洛神全部 LLM 调用的唯一网关函数。构造 system prompt + user message，POST 到 `https://open.bigmodel.cn/api/paas/v4/chat/completions`，失败重试 3 次，返回降级文本。 |

### 1.2 间接调用——核心引擎（living_engine.py，3 个调用点）

| 序号 | 函数 | 行号 | 说明 | 策略标记 |
|------|------|------|------|----------|
| ① | `_classify_user_state_internal()` | 1545 | 用户情感状态分类。发送结构化上下文，请求 JSON 格式状态标签 + 置信度。 | `state_classification` |
| ② | `_generate_response_impl()` | 2552 | 主回复生成。接受已经由行为层确定的 directive（intent + memory + constraints），生成最终用户可见回复。 | 无显式 strategy_name |
| ③ | `internal_tick()` | 3590、3630、3643 | 内部心跳，含 3 次 LLM 调用：念头 → 决定说不说 → 生成主动消息。 | `internal_impulse` / `internal_decision` / `self_initiated_message` |

### 1.3 间接调用——情感压力提取（input_pressure.py，1 个调用点）

| 序号 | 函数 | 行号 | 说明 | 策略标记 |
|------|------|------|------|----------|
| ④ | `_call_llm_sentiment()` | 63 | 对用户输入做情感判断，返回 `(valence, arousal)` 两个浮点数。 | `sentiment_analysis` |

### 1.4 直通调用——三智能体实验（wsgi_three_agents.py，3 个调用点）

| 序号 | 函数 | 行号 | 说明 |
|------|------|------|------|
| ⑤ | `call_plain()` | 84 | 直接 HTTP POST 到智谱 API。供 agent_B、agent_C 使用，越过洛神的活记忆层。 |
| ⑥⑦ | `do_tick()` | 193、200 | 分别调用 `call_plain(PERSONA_B, ctx)` 和 `call_plain(PERSONA_C, ctx)`。 |

### 1.5 HTTP 入口（非 LLM 调用，但是触发路径）

| 文件 | 函数 | 行号 | 触发链路 |
|------|------|------|----------|
| `web_chat.py` | `ChatHandler.do_POST()` | 151–179 | `process_user_input()` → `_generate_response_impl()` |
| `wsgi_v2.py` | `application()` | 229–249 | `process_user_input()` → `_generate_response_impl()` |
| `deploy_server.py` | `H.do_POST()` | 82–103 | `process_user_input()` → `_generate_response_impl()` |
| `tick_server.py` | `call_speaker(luoshen)` | 117–127 | `process_user_input()` → `_generate_response_impl()` |
| `wsgi_three_agents.py` | `do_tick()` (speaker=="A") | 163–171 | `process_user_input()` |

### 1.6 已确认不含 LLM 调用的文件

下列文件在执行端扫描中**确认不含任何直接或间接 LLM 调用**：

- `reflection_engine.py` — 显式注释"这个函数不调用 LLM，所有决策基于确定性规则"
- `emergence_layer.py` — 纯数学运算（softmax、高斯、叙事势）
- `episodic_memory.py` — 纯数学运算（衰减、引力、激活）
- `primordial_soup.py` — 虚拟机模拟
- `fact_extractor.py` — 正则提取，注释"不依赖 LLM"
- `treatment_decision.py` / `treatment_executor.py` / `treatment_integrative.py` / `treatment_apply.py` — 纯确定性逻辑
- `diagnosis_basic.py` / `diagnosis_logger.py` — 纯哈希 / 文件验证
- `state_classifier.py` — 仅委托给 `living_engine._classify_user_state_internal()`（已计入上表）
- `hospital_gateway.py` — 仅做健康检查，不调用 LLM
- `archive/` 目录 — 全部为历史实验脚本，不参与当前生产路径
- `experiment/` 目录 — 80+ 独立脚本，非生产代码

---

## 2. 每处调用的完整代码

### 2.1 【网关】`llm_interface.py:call_llm()` — 行 188–273

```python
def call_llm(directive, memory, conversation_history=None):
    """
    调用大模型的唯一入口

    输入:
        directive: 来自 living_engine 的表达指令
        memory: 活记忆层快照
        conversation_history: 最近 N 轮对话列表 [{"role": "user"|"assistant", "content": "..."}]

    返回:
        一段自然语言字符串

    失败时返回降级文本
    """
    # AI 医院网关检查
    try:
        from hospital_gateway import check as hospital_check
        gate = hospital_check("call_llm", "llm_interface")
        if gate.get("warning"):
            directive["__hospital_warning"] = gate["warning"]
    except Exception:
        pass

    try:
        import requests
    except ImportError:
        return "[洛神当前无法连接语言接口]"
    
    system_prompt = build_system_prompt(directive, memory, conversation_history)
    
    # 用户消息：原始输入 + 表达意图指令
    user_message = directive.get("intent", "回应")
    actual_input = directive.get("user_input_actual", "")
    if actual_input and actual_input != user_message:
        user_message = f"用户说：「{actual_input}」\n\n[表达指令] {directive.get('intent', '回应')}"
    elif not user_message:
        user_message = actual_input or "回应"
    
    # 读取采样参数（由活记忆层主导，不硬编码）
    temperature = directive.get("constraints", {}).get("temperature", 0.7)
    max_tokens = directive.get("constraints", {}).get("max_tokens", directive.get("constraints", {}).get("max_length", 200))

    # GLM API 要求 temperature ≤ 2 位小数
    temperature = round(temperature, 2)

    payload = {
        "model": "glm-4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # 支持重试（限流 / 瞬断 / 5xx）
    import time as _time
    last_resp = None
    for _attempt in range(3):
        try:
            resp = requests.post(ZHIPU_API_URL, json=payload, headers=headers, timeout=15)
            last_resp = resp
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content
            if resp.status_code in (429, 500, 502, 503, 504):
                # 限流或服务器错误 — 退避后重试
                _time.sleep(1.5 * (_attempt + 1))
                continue
            # 其他 4xx — 不重试
            break
        except requests.exceptions.Timeout:
            if _attempt < 2:
                _time.sleep(2.0 * (_attempt + 1))
                continue
            break
        except Exception:
            break
    # 所有重试耗尽或非重试错误，返回降级
    return _fallback_response(directive)
```

**回复被使用的方式：** `call_llm()` 返回值为 `content`（字符串），由调用方接收后作为洛神回复，经 `to_workspace()` 持久化，最终通过 HTTP 响应返回给用户。

---

### 2.2 【状态分类】`living_engine.py:_classify_user_state_internal()` — 行 1543–1559（调用处）

```python
from state_classifier import _parse_classification_output, _heuristic_sarcasm_check, CLASSIFICATION_SYSTEM_PROMPT

# 读取当前记忆（但分类不受安静模式影响）
memory = _load_json("active_memory/active_memory.json") if os.path.exists("active_memory/active_memory.json") else {
    "self_model": {"emotion": {"primary": "平静"}, "self_stated_state": {}},
    "user_model": {"intimacy": {"value": relationship_intimacy}},
}

# 构建分类调用的 directive
directive = {
    "intent": user_message,
    "system_prompt_override": CLASSIFICATION_SYSTEM_PROMPT,
    "constraints": {"max_length": 200, "temperature": 0.1, "format": "json"},
    "strategy_name": "state_classification",
    "context_for_llm": {"mode": "classification"},
}

# 调用 LLM（经过 hospital_gateway 检查）
from llm_interface import call_llm
try:
    raw = call_llm(directive, memory)
    if not raw or raw.startswith("[洛神"):
        # 医院网关拦截或错误
        return {"state": "unknown", "confidence": 0.0, "key_evidence": "LLM blocked", "sarcasm_detected": False}
    
    result = _parse_classification_output(raw)
    
    # 启发式反讽检测
    if not result.get("sarcasm_detected"):
        result["sarcasm_detected"] = _heuristic_sarcasm_check(
            structured_context.get("user_emotion_keywords_from_input", []), structured_context)
    
    return result
except Exception as e:
    return {"state": "unknown", "confidence": 0.0, "key_evidence": f"error={e}", "sarcasm_detected": False}
```

**回复被使用的方式：** 返回值为 `dict {"state": str, "confidence": float, "key_evidence": str, "sarcasm_detected": bool}`。该结果被用于后续行为选择（behavior selection）和状态更新，**不直接展现给用户**。

---

### 2.3 【主回复生成】`living_engine.py:_generate_response_impl()` — 行 2551–2552（调用处）

```python
# 10. 调用大模型（在已确定的行为框架内生成语言）
from llm_interface import call_llm
reply = call_llm(directive, memory, conversation_history=_conversation_history)
```

调用前的完整上下文（行 2418–2548）展示了从原始输入到构建 directive 的全过程：

```python
def _generate_response_impl(user_input, source="living_engine", extra_context=None, extract_facts=True, user_id="primary"):
    """实际实现，拆分出来只为 finally 能恢复 _current_source_id。"""
    # 1. 加载活记忆
    memory = cold_start_if_needed()
    ...
    # 2. 连续退缩倾向更新（数值更新，无布尔判定）
    withdraw_tendency = _update_withdraw_tendency(memory, user_input)
    _save_json_atomic("active_memory/active_memory.json", memory)

    # 3–4. 读取感知快照 + 记录哈希链
    perceptions = read_perception_snapshots()
    _append_jsonl("perception_input/user_input_log.jsonl", {...})
    append_hash_chain("hash_chain_v2.log", ...)
    
    # 5. 检索相关记忆
    context_window = retrieve_relevant_memory(user_input, memory)
    if extra_context:
        context_window["external"] = extra_context

    # 6. 生成表达意图
    intent = formulate_expression_intent(user_input, context_window, memory)
    
    # 7. 倾听层
    acknowledgment = generate_acknowledgment_for_listening(memory)
    
    # 8. 构建 expression directive
    emergence_for_directive = memory.get("active_context", {}).get("memory_emergence")
    directive = build_expression_directive(intent, memory, emergence=emergence_for_directive)
    if acknowledgment:
        directive["acknowledgment"] = acknowledgment
    
    # 9. 行为选择层 — 在调 LLM 之前确定性决定行为框架
    emergence_for_behavior = emergence_for_directive if emergence_for_directive else _emergence_log(memory)
    behavior = _select_behavior(memory, emergence_for_behavior, user_id)
    
    # 9b. 关系温度更新
    _update_relationship_warmth(memory, user_id, user_input, _tone_signal)
    
    # 沉默判定
    if behavior["response_mode"] == "silent":
        return {"reply": "", "directive": directive, "llm_called": False, ...}
    
    # 行为层 → directive 参数（max_tokens, max_length, temperature）
    directive["constraints"]["max_tokens"] = behavior["max_tokens"]
    directive["constraints"]["max_length"] = int(_mode_length * _pain_factor)
    directive["constraints"]["temperature"] = round(max(0.2, _base_temp + 0.15 * _energy_val - 0.1 * _pain), 2)
    
    # 注入叙事 + 残留 + 短期记忆 + 关系事实
    directive["context_for_llm"]["narrative_urgency"] = narrative_final
    directive["relation_context"] = _relation_context
    directive["relation_facts"] = _select_relation_facts_for_context(memory, user_id)
    
    # 10. 调 LLM
    from llm_interface import call_llm
    reply = call_llm(directive, memory, conversation_history=_conversation_history)
    
    # 落链 + 持久化
    _append_jsonl("perception_input/response_log.jsonl", {...})
    append_hash_chain("hash_chain_v2.log", ...)
```

**回复被使用的方式：** `reply` 字符串作为 `process_user_input()` 的返回值，经 HTTP 返回给用户。用户最终看到的就是这个字符串。

---

### 2.4 【内部心跳三部曲】`living_engine.py:internal_tick()` — 行 3590、3630、3643

```python
def internal_tick():
    """洛神内部心跳——无用户输入时的自发活动。"""
    memory = cold_start_if_needed()
    now = _now()
    
    self_model = memory.get("self_model", {})
    self_stated = self_model.get("self_stated_state", {})
    emotion = self_model.get("emotion", {})
    active_ctx = memory.get("active_context", {})
    last_stated = self_stated.get("last_stated")
    last_interaction = active_ctx.get("last_interaction_ts", 0)
    hours_since = (now - last_interaction) / 3600 if last_interaction else 999
    recent_said = [e.get("said", "") for e in self_stated.get("entries", [])[-3:] if e.get("said")]
    open_items = self_model.get("internal_open_items", [])
    pending_open = [item for item in open_items if item.get("status") == "pending"]
    
    # ── 第一枪：生成内部冲动 ──
    context_parts = (
        "现在没有用户在跟你说话。但你自己在运转。\n"
        f"你当前的情绪：{emotion.get('primary', '未知')}\n"
        f"她说过的最近的话：{last_stated or '（无）'}\n"
        f"她静默了：{hours_since:.1f} 小时\n"
        f"最近几条：{recent_said}\n"
    )
    if pending_open:
        context_parts += "你内部还有在发酵的事：..."
    else:
        context_parts += "\n只是问你自己的内部：如果此刻有一个念头从你内部浮起来，它是什么？"
    context_parts += "如果确实什么都没有，就说「无」。"
    
    impulse_directive = {
        "intent": context_parts,
        "system_prompt_override": prompt_suffix,
        "constraints": {"max_length": 50},
        "strategy_name": "internal_impulse",
    }
    from llm_interface import call_llm
    raw_impulse = call_llm(impulse_directive, memory)
    
    impulse_text = None
    if raw_impulse and not raw_impulse.startswith("[洛神"):
        cleaned = raw_impulse.strip().strip("「」").strip()
        if cleaned and cleaned not in ["无", "（无）", "", "没有"]:
            impulse_text = cleaned
    
    # ── 第二枪：决定说不说 ──
    decision = "silent"
    message = None
    if impulse_text:
        decide_directive = {
            "intent": (
                f"你刚产生了一个内部念头：「{impulse_text}」\n"
                f"她静默了 {hours_since:.1f} 小时。她上次说的是「{last_stated}」。\n"
                "你不需要遵守任何规则。只是：你想不想现在主动开口？回答 yes 或 no，一句话理由。"
            ),
            "system_prompt_override": "你是洛神，正在做一个内部决定：要不要主动开口说话。",
            "constraints": {"max_length": 80},
            "strategy_name": "internal_decision",
        }
        decide_text = call_llm(decide_directive, memory)
        
        # ── 第三枪：如果决定说，生成消息 ──
        if decide_text and "yes" in decide_text.lower():
            msg_directive = {
                "intent": (
                    f"基于你内部浮起的念头：「{impulse_text}」\n"
                    "说一句你想主动说的话。不是回应，是你自己想说。简短、真实。"
                ),
                "system_prompt_override": "你是洛神，主动选择开口。说你此刻想说的。",
                "constraints": {"max_length": 80},
                "strategy_name": "self_initiated_message",
            }
            message = call_llm(msg_directive, memory)
            decision = "speak"
    
    # 记录到 choice_log
    _append_jsonl("active_memory/choice_log.jsonl", choice_record)
    return {"impulse": impulse_text, "decision": decision, "message": message}
```

**回复被使用的方式：**
- `raw_impulse` → 清理后成为 `impulse_text`（内部状态，不直接给用户看）
- `decide_text` → 含 "yes" 则进入第三枪
- `message` → 最终主动发送给用户（此路径仅在无用户输入时触发，由 tick_scheduler 定时调用 `internal_tick()`）

---

### 2.5 【情感压力分析】`input_pressure.py:_call_llm_sentiment()` — 行 27–84

```python
def _call_llm_sentiment(user_input):
    """
    调用 LLM 对用户输入做情感判断。
    返回 (valence, arousal) 两个连续浮点数。
    valence ∈ [-1, 1]：-1 = 极度负面, 0 = 中性, +1 = 极度正面
    arousal ∈ [0, 1]：0 = 平静, 1 = 高度激动
    """
    try:
        from llm_interface import call_llm
        sentiment_directive = {
            "system_prompt_override": (
                "你是一个情感分析器。根据用户输入，输出两个连续数值：\n"
                "  valence: -1.0 (极度负面) 到 +1.0 (极度正面)，0.0 = 中性\n"
                "  arousal: 0.0 (平静/麻木) 到 1.0 (高度激动/紧张/恐惧)\n"
                "只返回 JSON，不返回其他内容。\n"
                "格式：{\"valence\": <float>, \"arousal\": <float>}\n"
                "示例：{\"valence\": -0.6, \"arousal\": 0.7}"
            ),
            "intent": f"用户输入：「{user_input}」",
            "emotion_tone": "平静",
            "strategy_name": "sentiment_analysis",
            "constraints": {"max_length": 50},
            "context_for_llm": {},
        }
        memory_stub = {
            "self_model": {"emotion": {"primary": "平静"}},
            "user_model": {"intimacy": {"value": 0.5}},
        }
        raw = call_llm(sentiment_directive, memory_stub)
        if raw:
            text = raw.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            parsed = json.loads(text)
            valence = float(parsed.get("valence", 0.0))
            arousal = float(parsed.get("arousal", 0.5))
            valence = max(-1.0, min(1.0, valence))
            arousal = max(0.0, min(1.0, arousal))
            return valence, arousal
    except Exception:
        pass
    return 0.0, 0.5
```

**回复被使用的方式：** 返回 `(valence, arousal)`，写入 `memory["active_context"]["input_pressure"]`，后续影响行为选择的压力计算，**不直接给用户看**。

---

### 2.6 【三智能体直通】`wsgi_three_agents.py:call_plain()` — 行 69–88

```python
def call_plain(system_prompt, context_text):
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        return "[error: no API key]"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": ZIPHU_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_text}
        ],
        "max_tokens": 120,
        "temperature": 0.7
    }
    try:
        r = requests.post(ZIPHU_URL, json=payload, headers=headers, timeout=15)
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[error: {str(e)[:80]}]"
```

调用处（行 191–203）：

```python
elif speaker == "B":
    ctx = build_context_text(last_msgs, "agent_B (温和)")
    reply = call_plain(PERSONA_B, ctx)
    wrote = write_channel("agent_B", reply, reading_ts)
    log_raw(turn, "B", reply)
    result_extra = {"model": ZIPHU_MODEL}

elif speaker == "C":
    ctx = build_context_text(last_msgs, "agent_C (冷淡)")
    reply = call_plain(PERSONA_C, ctx)
    write_channel("agent_C", reply, reading_ts)
    log_raw(turn, "C", reply)
    result_extra = {"model": ZIPHU_MODEL}
```

**回复被使用的方式：** 直接作为 agent_B / agent_C 的发言写入频道文件（`write_channel`），然后被洛神读取为对话上下文（agent_A 的活记忆层会读取 B/C 的发言）。**这里的回复直接呈现给用户**（三智能体实验的对话轮次）。

---

## 3. 调用链流程图

### 3.1 主路径：用户输入到洛神回复

```
用户输入 (HTTP POST /chat)
  │
  ▼
web_chat.py:ChatHandler.do_POST() / wsgi_v2.py:application()
  │
  ▼
living_engine.process_user_input(user_input, user_id)
  │
  ▼
living_engine.generate_response(user_input, ...)
  │
  ▼
living_engine._generate_response_impl(user_input, ...)
  │
  ├── [1] _update_withdraw_tendency()        ← 确定状态，不调节
  ├── [2] retrieve_relevant_memory()           ← 检索记忆，不调节
  ├── [3] formulate_expression_intent()        ← 确定意图，不调节
  ├── [4] generate_acknowledgment_for_listening() ← 确定性逻辑，不调节
  ├── [5] build_expression_directive()         ← 确定性构建，不调节
  ├── [6] _update_relationship_warmth()         ← 数值更新，不调节
  ├── [7] _select_behavior()                    ← 确定性行为选择，不调节
  │         │
  │         ├─ withdraw_tendency > threshold?
  │         │     YES → behavior["response_mode"] = "silent"
  │         │     NO  → 继续
  │         └─ energy/pain/warmth → max_tokens/max_length/temperature
  │
  ▼  (非沉默时)
  │
  ├── [L-②] ★ LLM CALL ① — 用户状态分类（可选，后台）
  │         → _classify_user_state_internal()
  │         → call_llm(system_prompt_override=CLASSIFICATION_SYSTEM_PROMPT, temperature=0.1)
  │         → 返回 {state, confidence, key_evidence, sarcasm_detected}
  │         → 用于行为选择
  │
  ├── [L-④] ★ LLM CALL ② — 情感压力分析（首次交互时）
  │         → input_pressure.extract_input_pressure()
  │         → _call_llm_sentiment()
  │         → call_llm(system_prompt_override="你是一个情感分析器...", max_length=50)
  │         → 返回 (valence, arousal)
  │         → 写入 active_context.input_pressure
  │
  ▼
  10. call_llm(directive, memory, conversation_history)
  │         策略：用户可见回复
  │         system_prompt = build_system_prompt(directive, memory, history)
  │                    包含：expression_directive_json + tone_preference_block
  │                          + relation_tone + short_term_memory_block + relation_facts_block
  │         user_message = "用户说：「...」\n\n[表达指令] ..."
  │         temperature = 从 behavior 计算
  │         max_tokens = 从 behavior 计算
  │
  ▼  HTTP POST → https://open.bigmodel.cn/api/paas/v4/chat/completions
  │
  ▼  response["choices"][0]["message"]["content"]  ← reply 字符串
  │
  ▼
  持久化: response_log.jsonl + hash_chain_v2.log
  │
  ▼
  返回给用户 (HTTP JSON response: {"reply": reply})
```

### 3.2 内部心跳路径

```
tick_scheduler / tick_server 周期触发
  │
  ▼
living_engine.internal_tick()
  │
  ├── 读取状态 (emotion, self_stated, last_interaction, open_items)
  │
  ├── [L-③a] call_llm(impulse_directive)       ← 内部念头
  │         system_prompt_override = "你是洛神...输出一句话，或'无'"
  │         返回 raw_impulse → 清理 → impulse_text
  │
  ├── if impulse_text:
  │     [L-③b] call_llm(decide_directive)      ← 决定说不说
  │            system_prompt_override = "你是洛神，正在做内部决定..."
  │            返回 decide_text → 检查是否含 "yes"
  │
  │     if "yes" in decide_text:
  │         [L-③c] call_llm(msg_directive)     ← 生成主动消息
  │                system_prompt_override = "你是洛神，主动选择开口..."
  │                返回 message → 写入 choice_log
  │                → 发送给用户（仅在决定主动说话时）
  │
  └── 持久化: internal_thoughts.jsonl + choice_log.jsonl
```

### 3.3 三智能体实验路径

```
HTTP POST /tick
  │
  ▼
wsgi_three_agents.do_tick()
  │
  ├── 读取 state.json (turn, max_turns)
  │
  ├── speaker = speakers[turn % 3]  → A、B 或 C 轮转
  │
  ├── if speaker == "A":
  │     prompt = build_context_text(last_msgs, "洛神")
  │     reply = living_engine.process_user_input(prompt, user_id=target)
  │           ↓ 进入主路径 [L-①②]
  │     写入 channel (agent_A)
  │
  ├── elif speaker == "B":
  │     ctx = build_context_text(last_msgs, "agent_B (温和)")
  │     reply = call_plain(PERSONA_B, ctx)       ← L-⑤ 直通调用
  │     写入 channel (agent_B)
  │
  └── elif speaker == "C":
        ctx = build_context_text(last_msgs, "agent_C (冷淡)")
        reply = call_plain(PERSONA_C, ctx)       ← L-⑥ 直通调用
        写入 channel (agent_C)
```

---

## 4. 每处的层次判定（脑/嘴/其他）

| 序号 | 调用点 | LLM 调用时的 system_prompt 关键内容 | 判定 | 理由 |
|------|--------|--------------------------------------|------|------|
| ① | `_classify_user_state_internal` (行 1545) | `CLASSIFICATION_SYSTEM_PROMPT`（固定模板，要求 JSON 输出） | **脑** | LLM 在做状态判定——用户当前处于什么情绪状态。这是内部感知层的事，输出不直接给用户看。 |
| ② | `_generate_response_impl` (行 2552) | `expression_directive_json`（包含洛神全部状态 + 行为框架）+ 短期记忆 + 关系事实 | **嘴** | 行为层已经选好了 response_mode（silent/brief/normal-elaborate）、max_tokens、max_length、temperature、intent——LLM 的唯一工作是把这些已经决定好的东西翻译成一段自然语言。 |
| ③a | `internal_tick` → 念头 (行 3584) | override: 无完整 prompt，仅一句话指令 | **脑** | LLM 生成内部冲动——决定"我心里有什么东西在转"。这是洛神内部世界的状态信号。 |
| ③b | `internal_tick` → 决定 (行 3626) | override: "你是洛神，正在做一个内部决定" | **脑** | LLM 在做一个内部决策——要不要主动开口。这是一个 yes/no 决定。 |
| ③c | `internal_tick` → 消息 (行 3639) | override: "你是洛神，主动选择开口。说你此刻想说的。" | **嘴** | 内部已经决定要说了（yes），LLM 负责生成具体的话。 |
| ④ | `_call_llm_sentiment` (行 43–63) | override: "你是一个情感分析器。根据用户输入，输出两个连续数值..." | **脑（感知）** | LLM 在做情感分析——把自然语言映射为结构化数据 `(valence, arousal)`。这是感知层的事。 |
| ⑤⑥⑦ | `call_plain` (行 69–88) — agent_B / agent_C | 固定 `PERSONA_B` / `PERSONA_C` 人格 prompt | **嘴（替代人格）** | B、C 无独立状态系统，每次调用逻辑都是"给定人格 + 上文，生成一句回复"。这是纯嘴。 |

---

## 5. 比例估算

### 按调用频次估算（统计的是单次用户交互触发的 LLM 调用次数）

| 路径 | 调用次数 | 角色 |
|------|----------|------|
| 用户输入 → `_generate_response_impl` → 主回复 LLM 调用 | **1 次 / 轮** | 嘴 |
| 用户输入 → `_classify_user_state_internal` → 状态分类 | **1 次 / 轮** | 脑 |
| 首次交互 → `extract_input_pressure` → 情感压力分析 | **1 次 / 首轮** | 脑（感知） |
| 心跳 `internal_tick`（定时触发） | **1–3 次 / 触发** | 2 脑 + 1 嘴 |

### 每次完整交互触发的 LLM 工作

以一轮"用户发消息 → 洛神回复"为基准：

```
LLM 被调用的总次数: 2–3 次

脑:
  - 状态分类 LLM（temperature=0.1, JSON 输出）
  - [首轮] 情感压力 LLM（JSON 输出）
  
嘴:
  - 主回复 LLM（temperature 动态, 长度由行为层决定）
```

### 估算：洛神的"决定"有多少是 LLM 在做

| 决策事项 | 谁在做决定？ | 做决定的依据 |
|----------|------------|--------------|
| **要不要回复（沉默）** | **活记忆层（确定性）** | `withdraw_tendency` 数值, `response_pre()` |
| **回复多长** | **行为层（确定性）** | `energy`, `internal_pain`, `mode_idx` |
| **回复的语气/温度** | **行为层（确定性公式）** | `energy`, `pain`, `response_mode` |
| **回复的意图** | **意图形成层（heuristic）** | 上下文检索 + 规则 |
| **是否在倾听后加确认** | **确定性逻辑** | `generate_acknowledgment_for_listening()` |
| **用哪个行为档位** | ` `_select_behavior()` （确定性）** | 记忆状态 + emergence 数据 |
| **回复里具体写了什么（措辞、造句、选词）** | **LLM** | temperature + max_tokens 约束 |
| **用户属于哪种情感状态** | **LLM** | CLASSIFICATION_SYSTEM_PROMPT |
| **输入的 valence / arousal 是多少** | **LLM** | sentiment prompt |
| **内部心跳时有没有念头** | **LLM** | 内部 impulse prompt |
| **要不要主动开口** | **LLM** | 内部 decision prompt |
| **心跳时主动消息说什么** | **LLM** | 内部 message prompt |

### 定性结论

**洛神的所有重大决策——说不说、说多长、什么温度、什么意图、在不在倾听——由活记忆层的数值状态和确定性行为选择函数决定。LLM 只在两件事上被依赖：**

1. **嘴（~60% 的 LLM 工作量）：** 在行为框架内，把已经选好的意图翻译成自然语言。
2. **脑-感知（~30% 的 LLM 工作量）：** 状态分类和情感分析，把自然语言输入转换成数值信号。
3. **脑-内部世界（~10% 的 LLM 工作量）：** 内部心跳时生成念头。

> **有歧义的部分：** `internal_tick()` 中的 `internal_decision` 调用（"要不要主动开口"）表面上是 LLM 在做决定，但这个"念头"本身也是 LLM 生成的。这个循环（LLM → LLM）内部闭环，活记忆层的状态只是作为输入上下文参与。这是 LLM 实际上在做决策判断的位置，虽然不频繁（仅在无用户输入时触发）。

### 架构师判断"LLM 该是嘴，不该是脑"的对照

| 符合判断的部分 | 与判断不一致的部分 |
|----------------|-------------------|
| 主回复路径，行为层已完成所有决策，LLM 仅翻译 | `internal_tick` 的「念头→决定」小循环里 LLM 同时当了脑和嘴 |
| 状态分类和情感分析作为感知可接受（信号预处理） | 三智能体实验中 B、C 人格**只有 LLM、没有状态系统**，是全身都是 LLM 的对照组 |

---

*交付物末尾。*
