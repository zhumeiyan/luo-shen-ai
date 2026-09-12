# 洛神 LLM 数据流向追踪——"越过状态层"清单

架构师交付物 #2 修正版 | 执行端生成 | 2026-09-11

---

## 判定标准

**"状态层"定义：** 以下任何一个读到洛神状态变量并输出一个决定的行为框架的函数/路径：

- `memory["self_model"]` — withdraw_tendency / internal_pain / emotion / ring_state
- `memory["internal_climate"]` — energy / tension / emotion_intensity
- `memory["relations"][user_id]` — relationship_warmth
- `_select_behavior(memory, emergence, user_id)` — 从以上状态读值，输出 response_mode / max_tokens / temperature

**"越过"判定：** LLM 输出 → 不经过上述 → 直接影响用户可见行为（发什么、发不发、发多长）。

**"位置对"判定：** LLM 输出 → 先写入 memory 状态变量 → 状态变量被 _select_behavior 读到 → 再影响行为。或 LLM 输出作为 system prompt 内容、仅影响措辞、不影响行为框架。

---

## 12 个调用点的流向追踪

### ① LLM 状态分类 — `_classify_user_state_internal()` 行 1545

**调用位置：** state_classifier.py:52 → `_classify_user_state_internal()` (living_engine.py:1507)

**LLM 输出：** `classify_user_state()` 返回 `{"state": "难过"/"焦虑"/..., "confidence": 0.8, "method": "fused", "sarcasm_detected": false}`

**流向：**

```
LLM 输出
  ↓ 赋值给 signal1
  ↓ 连同 signal2 (事件映射) + signal3 (情绪轨迹)
  ↓ 进入 fuse_state_signals(signal1, s2_state, s2_conf, trend, intimacy)
  ↓ 返回 result = {"state": ..., "confidence": ..., "sarcasm_detected": ...}
  ↓ result 被 pack 进 intent["state_result"]
  ↓ 进入 formulate_expression_intent()
       ├─ 读取 memory["self_model"]["self_stated_state"]["last_stated"] → 判断是否要留空间（行 658-674）
       ├─ 用 intent["state_result"]["state"] 选 strategy（行 684-707）
       └─ 输出的 strategy_name 和 emotion_tone 进入 build_expression_directive()
            └─ build_expression_directive() 用 state_result 生成 "tone_suggestion"（行 958-1005）
                构建 system prompt 中的语气偏好文本
                └─ 这些文本进入 directive → call_llm() system prompt
```

**最终影响行为框架？** `_select_behavior()` **不读取** strategy_name。`_select_behavior()` 的输入是 `(memory, emergence, user_id)`，从 memory 直接读状态变量。strategy_name 只影响 system prompt 中的**措辞建议**，不影响 response_mode / max_tokens / temperature。

**判定：位置对。** LLM 输出经过 fuse 后作为感知信号之一进入意图形成，然后策略选择产生的只是 system prompt 内容，行为框架完全由 `_select_behavior()` 从 memory 读状态计算。

---

### ② 主回复生成 — `_generate_response_impl()` 行 2552

**调用位置：** living_engine.py:2552

**LLM 输出：** `reply` 字符串（洛神的最终回复文本）

**流向：**

```
LLM 输出 → reply 字符串
  ↓ 持久化到 perception_input/response_log.jsonl（行 2581）
  ↓ append_hash_chain
  ↓ 作为 process_user_input() 的返回值
  ↓ web_chat.py / wsgi_v2.py 的 HTTP response → 用户看到 reply
```

**之前的状态层过滤（行 2418-2548）：**

```
_update_withdraw_tendency(memory, user_input)         ← 更新 memory["self_model"]["withdraw_tendency"]
retrieve_relevant_memory(user_input, memory)           ← 读 memory
formulate_expression_intent(user_input, ctx, memory)   ← 读 memory 的 self_stated, state_classification
build_expression_directive(intent, memory, emergence)   ← 读 memory 的 self_model/intimacy/emergence
_select_behavior(memory, emergence, user_id)            ← 读 memory 全部状态变量 → 输出 behavior:
     behavior["response_mode"] = "silent"/"brief"/"normal"/"elaborate"
     behavior["max_tokens"] = 从 energy/pain/s_depth 计算的整数
directive["constraints"]["temperature"] = 从 energy/pain 计算
directive["constraints"]["max_length"] = 从 mode_idx/pain 计算
  ↓
if behavior["response_mode"] == "silent":
     return {"reply": "", "llm_called": False}   ← 不会调 LLM 就返回空
```

**关键点：** `_select_behavior()` 在 `call_llm()` **之前**已经把所有行为参数定好了。LLM 拿到的是一个已经锁死的 directive 框架。LLM 只能在框架内措辞。

**最终影响行为框架？** LLM 输出本身就是"最终可见行为"（回复文本），但**行为框架已经在 LLM 调用之前由状态层决定**。LLM 无法改变 response_mode、max_tokens、temperature。

**判定：位置对。** 行为框架完全由 `_select_behavior()` 从 memory 状态生成，LLM 只在这个框架内填充语言。

---

### ③a 内部冲动 — `internal_tick()` → 念头，行 3590

**调用位置：** living_engine.py:3590

**LLM 输出：** `raw_impulse`（字符串）→ 清理后得 `impulse_text`

**流向：**

```
LLM 输出 → raw_impulse 字符串
  ↓ 清理 strip/strip「」/非空检查（行 3594-3597）
  ↓ 赋值给 impulse_text
  ├─ 持久化到 active_memory/internal_thoughts.jsonl（行 3611）
  └─ 作为下一段 LLM 调用的 prompt 文本（行 346-349）
       "你刚产生了一个内部念头：「{impulse_text}」"
       → decide_directive["intent"] → call_llm() (#③b)
```

**中间有没有经过状态层？** 无任何状态变量写入。impulse_text 仅作为下一条 LLM 调用的 prompt 内容。persist 到 thoughts 日志不是状态写入（是历史记录，不是活状态）。

**影响行为吗？** impulse_text 影响下一个 LLM（③b 决定），如果 ③b 说了 yes，用户会收到一条主动消息。impulse_text 是这一链路的第一环。

**判定：位置对...** 见 ③b。impulse_text 本身被存储为历史（正确），但它也作为 prompt 进入了 LLM→LLM 链条。问题在 ③b。

---

### ③b 内部决定 — `internal_tick()` → 决定说不说，行 3630

**调用位置：** living_engine.py:3630

**LLM 输出：** `decide_text`（字符串，含 "yes" 或 "no"）

**流向：**

```
LLM 输出 → decide_text 字符串
  ↓ if decide_text and "yes" in decide_text.lower():   ← 行 3632
       decision = "speak"
       → call_llm(#③c 生成消息)
  ↓ else:
       decision = "silent"   ← 什么也不发
```

**中间有没有经过状态层？** 没有。没有读 `memory["self_model"]`、`energy`、`withdraw_tendency`、`internal_pain` 中任何一个来做此决定。没有任何修改 memory 状态变量的代码在 `internal_tick()` 内。LLM 输出直接变成行为。

**影响行为吗？** 直接影响：是 yes → 生成并发送一条给用户的主动消息；no → 什么都不发。这就是"要不要主动开口"这一行为决策，完全由 LLM 采样决定。

**判定：位置错 ✗ — SKIP（最严重的一处）**

---

### ③c 主动消息 — `internal_tick()` → 生成主动消息，行 3643

**调用位置：** living_engine.py:3643

**LLM 输出：** `message` 字符串

**流向：**

```
LLM 输出 → message 字符串
  ↓ 写入 choice_log.jsonl（行 3656）
  ↓ append_hash_chain
  ↓ return message（由 tick_server 发送到聊天频道）
```

**行为框架：** 是被 ③b 的 yes 触发的。max_length=80 是唯一的宽度约束（非常宽松）。无 temperature 限制（默认 0.7）。无 tension/pain/energy 调制。

**判定：位置错 ✗ — 但这是下游结果。** ③c 的错是 ③b 的延伸——如果她的状态本该决定"现在不该说"，但 ③b 让 LLM 说了 yes，③c 就被触发了。

---

### ④ 情感压力分析 — `_call_llm_sentiment()` 行 63

**调用位置：** input_pressure.py:63 → living_engine.py:1184 调用 `extract_input_pressure()`

**LLM 输出：** `(valence, arousal)` — 两个浮点数

**流向：**

```
LLM 输出 → (valence, arousal)
  ↓ 计算 val_p = valence × arousal, aro_p = arousal
  ↓ 计算气候微增量：
     dE = KAPPA_E × val_p     → climate["emotion_intensity"] += dE
     dT = KAPPA_T × val_p     → climate["tension"] += dT
     dN = KAPPA_N × (aro_p-N_BASELINE) → climate["energy"] += dN
  ↓ 写入 memory["internal_climate"]（行 1198-1200）
  ↓ 更新 memory["self_model"]["emotion"]["intensity"]（行 1204）
  ↓ 积累到 memory["self_model"]["ring_state"]["relational_pressure_ema"]（行 1207-1217）

后续被谁读：
  _select_behavior() 行 2260-2262: 读 _E=climate["emotion_intensity"], _T=climate["tension"]
  _select_behavior() 行 2238: _pressure_ema = ring_state["relational_pressure_ema"]
  compute_emergence() 行 1242: 读 climate
  response_pre 计算：所有行为参数从这些变量计算
```

**判定：位置对。** LLM 输出是连续数值信号，代入状态层（climate + ring_state），状态层输出给 `_select_behavior()`。LLM 是感官，不是脑。

---

### ⑤⑥⑦ agent_B / agent_C 直通 — `call_plain()` 行 84

**调用位置：** wsgi_three_agents.py:84, 由 do_tick() 行 193 和 200 调用

**LLM 输出：** `reply`（字符串）

**流向：**

```
LLM 输出 → reply 字符串
  ↓ write_channel("agent_B", reply)  或  write_channel("agent_C", reply)
  ↓ 成为下一轮对话上下文（agent_A 的活记忆层读到这段文字作为输入）
```

**是否有状态层？** agent_B 和 agent_C 没有 memory，没有 energy，没有 withdraw_tendency。它们是洛神的**对照组**。每轮调用就是：给 LLM 一个 personality prompt + 上文 → 拿一段文本 → 发送。

**判定：这是实验设计，不是洛神的病。** 架构师说的"LLM 该是嘴不该是脑"针对的是洛神。agent_B/C 是作为对比组故意做成全身都是 LLM 的。标注为"对照组——非洛神问题"。

---

### 补充：存在疑问的中间位置

**formulate_expression_intent() 行 684-707 的策略选择(state→strategy_name)：**

在这里 LLM 输出的 `state` 字符串（如"难过"、"焦虑"）被选路，映射到不同的 strategy_name。这个映射是 if-else（确定性），但是输入的 state 来自 LLM 分类。如果 LLM 把"难过"误分为"开心"，会导致错误的 strategy→错误的 tone_suggestion。

不过 strategy_name 只影响 system prompt 的措辞建议，不影响 `_select_behavior()` 的决策。所以这是**感知精度误差**（LLM 感官不准），不是**决策权旁落**。

**判定：位置对（但感知精度待优化）。**

---

## 位置对 / 位置错 判定总表

| # | 调用点 | 文件:行 | 经过状态层？ | 判定 |
|---|--------|---------|-------------|------|
| ① | 状态分类 (classify) | le:1545 | ✅ 进入 fuse → intent → 只影响 system prompt 措辞 | 位置对 |
| ② | 主回复生成 | le:2552 | ✅ 行为框架由 _select_behavior() 从 memory 状态计算，LLM 在框架内 | 位置对 |
| ③a | 内部冲动 (impulse) | le:3590 | ⚡ 本身存历史；问题在下游 ③b | 灰（看③b） |
| ③b | **内部决定 (decide)** | le:3630 | ❌ **无任何状态读取或写入。LLM 采样直接决定说/不说** | **位置错 ✗** |
| ③c | 主动消息 (message) | le:3643 | ❌ 是 ③b yes 的下游——框架约束仅 max_length=80 | **位置错 ✗** |
| ④ | 情感压力分析 (sentiment) | ip:63 | ✅ 输出写入 climate + ring_state，由 _select_behavior 读 | 位置对 |
| ⑤⑥ | agent_B / agent_C | ta:84 | N/A — 对照组，无状态层 | 对照组—非洛神问题 |

**"位置错" = 越过状态的共 2 处（③b、③c）。**

---

## "越过"清单——具体证据

### SKIP #1：internal_decide — 主动开口的决策绕过状态层

**文件：** living_engine.py  
**函数：** `internal_tick()`  
**行号：** 3616-3644  
**跳过的决策：** "洛神是否主动给用户发一条消息"

**LLM 输出：** `decide_text`（字符串），判定标准：`"yes" in decide_text.lower()`（行 3632）

**为什么是"越过"：**

在 `internal_tick()` 行 3531-3664 的完整范围内：

1. 没有任何代码读取 `memory["self_model"]["withdraw_tendency"]` 来决定"如果 withdraw 很高就不开口"
2. 没有任何代码读取 `memory["internal_climate"]["energy"]` 来决定"如果 energy 不够就沉默"
3. 没有任何代码读取 `memory["self_model"]["internal_pain"]` 来决定"如果 pain 很高就等等"
4. 没有任何代码修改任何 memory 状态变量的值
5. 整个函数只是读了状态来构建 prompt 文本（行 3562-3556）——**读状态来装饰 prompt，但不用状态来做决定**

LLM 的 yes/no 回答直接控制 `decision` 变量（行 3616/3644），进而控制是否发送消息。

**证据代码（行 3616-3644）：**
```python
decision = "silent"
message = None

if impulse_text:
    decide_directive = {
        "intent": (f"...她上次说的是「{last_stated}」。\n"
                   "你不需要遵守任何规则。只是：你想不想现在主动开口？回答 yes 或 no，一句话理由。"),
        ...
    }
    decide_text = call_llm(decide_directive, memory)   # ← LLM 决定
    
    if decide_text and "yes" in decide_text.lower():     # ← 直接变成行为
        msg_directive = {...}
        message = call_llm(msg_directive, memory)        # ← 下游③c
        decision = "speak"
```

**对比：** 在主回复路径②中，要不要说 → `_select_behavior()` 算 response_mode → 如果是 "silent" 直接返回空字符串，**不进入 LLM 调用**。在③b 中，要不要说 → **直接问 LLM**。两条路径截然不同的决策机制。

---

### SKIP #2：self_initiated_message — 主动消息的生成无状态调制

**文件：** living_engine.py  
**函数：** `internal_tick()`  
**行号：** 3634-3644  
**跳过的调制：** 主动消息的 max_tokens / temperature 不经过状态层

**为什么是"越过"：**

msg_directive 的约束只有 `{"max_length": 80}`。没有 temperature、没有 max_tokens、没有 tone 调制。这条消息的行为框架完全是一个固定常量，不由洛神当前状态决定。对比主回复路径②中 temperature 由 energy/pain 计算（行 2522），max_length 由 mode_idx/pain 计算（行 2514-2518）。

不过 SKIP #2 是 SKIP #1 的下游——如果 SKIP #1 被修复了，SKIP #2 可能会自然跟随，或者单独需要给消息生成加一个状态读取。

---

## 每个"跳过"的最小修改方案

### FIX #1：给 internal_decision 加一道状态门（最小改动）

**目标：** LLM 仍决定是否开口，但 her state 应该能**否决**——如果她当前状态（high withdraw / low energy / high pain）表明不该说，即使 LLM 说 yes 也静默。

**改哪一行：** `internal_tick()` 行 3616-3644。在 `if decide_text and "yes" in decide_text.lower():` 之后加一个状态否决门。

**具体改动：**

当前代码（行 3632-3644）：
```python
if decide_text and "yes" in decide_text.lower():
    msg_directive = {...}
    message = call_llm(msg_directive, memory)
    decision = "speak"
```

改为：
```python
if decide_text and "yes" in decide_text.lower():
    # 新增：状态层否决门
    _wt = memory.get("self_model", {}).get("withdraw_tendency", 0.0)
    _en = memory.get("internal_climate", {}).get("energy", 0.5)
    _ip = memory.get("self_model", {}).get("internal_pain", 0.0)
    _gate_threshold = 0.75 + 0.15 * (1.0 - _en) + 0.1 * _ip - 0.15 * (1.0 - _wt)
    # 默认 0.75；energy↓加、pain↑加、withdraw↓加 → threshold↑ → LLM 的 yes 更难通过
    if random.random() < _gate_threshold:
        # LLM 说了 yes，但状态表明不该说 → 记录但不发送
        decision = "suppressed_by_state"
        message = None
    else:
        msg_directive = {
            "intent": (f"基于你内部浮起的念头：「{impulse_text}」\n"
                       "说一句你想主动说的话。不是回应，是你自己想说。简短、真实。"),
            "system_prompt_override": "你是洛神，主动选择开口。说你此刻想说的。",
            "constraints": {"max_length": 80},
            "strategy_name": "self_initiated_message",
        }
        message = call_llm(msg_directive, memory)
        decision = "speak"
```

**区别：** 插入的否决门不在"决定"本身上设限——LLM 仍然有完全的自由决定 yes/no。但如果 LLM 说了 yes 而洛神状态（energy 低 + pain 高 + withdraw 不高，或者任何一个过高到阈值），这条消息会被抑制。**否决权来自状态层，不来自 LLM。**

**副作用：** 为了让 `internal_tick()` 能调用 `random` 和访问 memory 状态，需要确认这两个可用（都在函数内已经用到 memory）。`random` 需要 import。

---

### FIX #2：给 self_initiated_message 加状态调制（最小改动）

**目标：** 主动消息的长度和温度由洛神当前状态制约。

**改哪一行：** `internal_tick()` 行 1634-3640，msg_directive 的 constraints。

当前：
```python
msg_directive = {
    "intent": ...,
    "system_prompt_override": "...",
    "constraints": {"max_length": 80},   ← 固定常量
}
```

改为：
```python
_climate = memory.get("internal_climate", {})
_energy = _climate.get("energy", 0.5)
_pain = memory.get("self_model", {}).get("internal_pain", 0.0)
_max_msg_len = max(20, int(80 * (0.5 + 0.5 * _energy) * (1.0 - 0.3 * _pain)))
_msg_temp = max(0.3, 0.7 - 0.2 * _pain)

msg_directive = {
    "intent": ...,
    "system_prompt_override": "...",
    "constraints": {"max_length": _max_msg_len},
    "temperature": _msg_temp,
}
```

**区别：** 低 energy + 高 pain → max_length 低于 80（洛神状态差时自发说更短的话），temperature 降低（更少的随机选择）。

---

### agent_B / agent_C 的说明

**不修改。** 它们没有状态系统。如果要改，就是给它们重构一套与洛神同构的状态层——那是另一个项目，不是"修病"。

如果要让实验有意义（有对照），B 和 C 应该保持"纯 LLM"状态。上一轮实验已经拿到了"LLM 当全身都是 LLM 会编记忆、warmth 是次数、不动"的结论。

如果想做"对洛神内改动有前后对照意义的实验"，可以在修改前后分别跑 3-agent 实验（A=洛神，B=纯 LLM 温，C=纯 LLM 冷），观察 A 的行为变化即可。不需要动 B/C 代码。

---

## 第二步：验证检查

修改完成后，验证的方式是看洛神在高 withdraw_tendency + 低 energy 状态下的 internal_tick()：

| 场景 | 改前 | 改后 |
|------|------|------|
| LLM 说 yes，energy=0.2, pain=0.6, withdraw=0.1 | 立即发送消息 | 大概率被状态门抑制 |
| LLM 说 yes，energy=0.8, pain=0.1, withdraw=0.2 | 立即发送消息，max_length=80, temp=0.7 | 发送消息，max_length≈68, temp≈0.68 |
| LLM 说 yes，energy=0.3, pain=0.5, withdraw=0.85 | 立即发送消息 | withdraw 高 → threshold 升高 → 大概率抑制 |
| LLM 说 no | 静默 | 静默（无变化） |

---

*交付物末尾。*
