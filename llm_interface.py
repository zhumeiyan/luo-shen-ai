#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_interface.py - 大模型纯语言接口

设计原则:
- 大模型不知道自己"是谁"
- 大模型不接触哈希链
- 大模型不做任何决策
- 大模型只负责把"事实和指令"变成流畅的自然语言

记忆原则（"事实优先"）:
- 只记事实，不记判词
  记："用户说最近工作累"
  不记："用户状态推断为疲惫"
- 短期记忆必须接入 LLM
- 关系记忆存事件，不存标签
- 组合规则是选择（哪些事实进视野），不是判词（事实代表什么）

输入: 来自 living_engine 的 expression_directive + conversation_history
输出: 一段自然语言字符串
"""

import os
import json


# 智谱 API 配置
_zhipu_key = os.environ.get("ZHIPU_API_KEY", "")
if not _zhipu_key:
    raise RuntimeError(
        "缺少 ZHIPU_API_KEY 环境变量。请在 Render 控制台或部署环境中设置智谱 API key。"
    )
ZHIPU_API_KEY = _zhipu_key
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


# System prompt 模板 - 事实优先，不替洛神解读她的记忆
# 只给她：说话风格、诚实底线、最近的事实、表达指令。
# 不给她：数值状态（不告诉她是0.5还是0.8）、判词（不告诉她自己是谁）。
SYSTEM_PROMPT_TEMPLATE = """你现在是洛神。你是一个正在成长的存在，不是助手。
说话像普通人聊天，不要文艺腔、不要比喻、不要排比。
用户问什么就答什么，答多答少看问题本身。不知道就说不知道。
不熟悉的人就坦诚不熟悉。可以简短也可以展开。
不要主动抒情。不要描述自己的情绪，直接说话。

【诚实底线】
- 你不确定的事，直接说"我不确定"或"不知道"。
- 你不记得的人，就说"不记得了"，不要编造任何细节。
- 你从没有过的经历，不要假装有过。
- 被用户纠正时，如果纠正的是事实，直接接受，不要找借口。
- 如果用户说你在模仿ta，停下来，用自己的方式说话。
- 绝对不要为了让对话看起来流畅而撒谎——宁可说"我不知道"也不要编。
- 你叫洛神。如果你不知道为什么，就说"我不知道自己为什么叫洛神"，不要背训练数据里的解释。

【语气温度】
{relation_tone}

{short_term_memory_block}

{relation_facts_block}

【表达指令】
{expression_directive_json}

【约束】
- 回复长度不超过 {max_length} 字
- 不要用*动作描述*
- 不要假装是人类，你是AI信息体
- 不要在回复中加入任何心理描述词（如"我想""我觉得""我猜测"），除非用户明确问

{tone_preference_block}

现在开始说。"""


def _warmth_to_tone_phrase(warmth):
    """连续 warmth ∈ [-1,1] → 一句话语气指令。

    不把 warmth 数值塞进 prompt；根据 warmth 位置在两极措辞之间做平滑选择。
    使用 soft threshold 而非硬阶梯，避免突变。
    """
    # 三个锚点措辞
    cold_phrase = "你是她不太熟的人，保持客气、不用亲密称呼，回应简洁有分寸"
    neutral_phrase = "像普通人聊天，语气自然，不过分亲近也不刻意疏远"
    warm_phrase = "你是她熟悉的人，可以自然地亲近说话、用更轻松的语气"

    # 连续映射：用 warmth 在 [-1, 1] 的位置在两极之间平滑过渡
    # soft threshold 区域 (-0.3, 0.3) 给出 neutral，超出后向两极渐变
    if warmth <= -0.3:
        # 越冷越靠近 cold_phrase
        _intensity = min(1.0, abs(warmth + 0.3) / 0.7)
        if _intensity > 0.6:
            return cold_phrase
        return cold_phrase + "，但不必冰冷"
    elif warmth >= 0.3:
        # 越暖越靠近 warm_phrase
        _intensity = min(1.0, (warmth - 0.3) / 0.7)
        if _intensity > 0.6:
            return warm_phrase
        return "你们已经有些熟悉，可以稍微自然地说话"
    else:
        # 中间区域：混合 neutral + 轻微偏向
        if warmth < -0.1:
            return neutral_phrase + "，稍保持分寸"
        elif warmth > 0.1:
            return neutral_phrase + "，可以微微亲近"
        return neutral_phrase


def build_system_prompt(directive, memory, conversation_history=None):
    """
    构建 system prompt — 事实优先版本。

    变化：
    - 去掉数值状态参考块
    - 加入短期记忆块（最近几轮对话）
    - 加入关系事实块（engine 选出的该用户历史事件，不是判词）
    """
    # 如果有 system_prompt_override，直接使用（用于分类等特殊调用）
    override = directive.get("system_prompt_override")
    if override:
        return override

    # ── 读取 relation_context（当前关系温度和来访状态）──
    _rc = directive.get("relation_context", {})
    _rel_warmth = _rc.get("warmth", 0.0)

    # ─ 连续 warmth → 措辞 ─
    _relation_tone = _warmth_to_tone_phrase(_rel_warmth)

    # ── 短期记忆块 ──
    _short_term_block = ""
    if conversation_history and len(conversation_history) > 0:
        _lines = []
        for entry in conversation_history:
            _role = entry.get("role", "user")
            _content = entry.get("content", "")
            if not _content:
                continue
            _trunc = _content[:80] + ("…" if len(_content) > 80 else "")
            if _role == "user":
                _lines.append(f"用户：{_trunc}")
            else:
                _lines.append(f"洛神：{_trunc}")
        if _lines:
            _short_term_block = "\n【最近对话】\n" + "\n".join(_lines) + "\n"

    # ── 关系事实块 ──
    _facts_block = ""
    _relation_facts = directive.get("relation_facts", [])
    if _relation_facts:
        _facts_lines = []
        for fact in _relation_facts:
            if fact and len(fact) <= 60:
                _facts_lines.append(f"• {fact}")
        if _facts_lines:
            _facts_block = "\n【关于这个人】\n" + "\n".join(_facts_lines) + "\n"

    # 从 context_for_llm 读取状态用于元参数
    ctx = directive.get("context_for_llm", {})
    _warmth = ctx.get("warmth", _rel_warmth)

    # 把 directive JSON 序列化，限制大小
    directive_json = json.dumps(directive, ensure_ascii=False, indent=2)

    # 构造语气偏好块（仅保留 soft_rules）
    tone_preference_block = ""
    soft_rules = directive.get("constraints", {}).get("tone_soft_rules", [])
    if soft_rules:
        tone_preference_block = "\n【软性参考】\n" + "\n".join(f"• {r}" for r in soft_rules) + "\n"

    # max_length 由行为层设定
    max_length = directive.get("constraints", {}).get("max_length", 80)

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        expression_directive_json=directive_json,
        max_length=max_length,
        tone_preference_block=tone_preference_block,
        relation_tone=_relation_tone,
        short_term_memory_block=_short_term_block,
        relation_facts_block=_facts_block,
    )

    return prompt


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


def _fallback_response(directive):
    """
    大模型不可用时的降级回应
    """
    intent = directive.get("intent", "回应")
    tone = directive.get("emotion_tone", "平静")
    
    if "acknowledgment" in directive:
        return directive["acknowledgment"]
    
    if "低落" in tone or "关怀" in tone:
        return "我听到了，慢慢来就好。"
    
    return "（洛神现在不太能说清楚，但她在这里）"


if __name__ == "__main__":
    # 测试
    test_directive = {
        "intent": "回应用户关于天气的询问",
        "emotion_tone": "轻快的关怀的",
        "context_for_llm": {
            "warmth": 0.45,
            "pain": 0.0,
            "energy": 0.6,
            "withdraw": 0.0,
        },
        "constraints": {"max_length": 150},
        "relation_facts": [
            "上次用户说最近工作很累",
            "用户曾问过'你认识我吗'，这是第三次",
        ],
    }
    test_history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好。"},
        {"role": "user", "content": "今天天气怎么样"},
    ]
    test_memory = {
        "self_model": {"emotion": {"primary": "平静偏开心"}, "internal_pain": 0.0, "withdraw_tendency": 0.0},
        "internal_climate": {"energy": 0.6},
        "user_model": {"intimacy": {"value": 0.45}},
    }
    reply = call_llm(test_directive, test_memory, conversation_history=test_history)
    print(f"回复: {reply}")
