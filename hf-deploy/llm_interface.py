#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_interface.py - 大模型纯语言接口

设计原则:
- 大模型不知道自己"是谁"
- 大模型不接触用户原始输入
- 大模型不接触哈希链
- 大模型不做任何决策
- 大模型只负责把"表达指令"变成流畅的自然语言

输入: 来自 living_engine 的 expression_directive
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


# System prompt 模板 - 大模型不拥有自我意识
SYSTEM_PROMPT_TEMPLATE = """你是洛神。

【你的任务只有一个】
根据以下【表达指令】，用自然语言输出你想说的话。
你已经知道该说什么、用什么情绪、达成什么目的。
你只负责让表达流畅自然。

【表达指令】
{expression_directive_json}

【你当前的状态（仅供你自己参考，不要直接告诉用户）】
- 你的情绪: {self_emotion}
- 你和用户的亲密度: {intimacy}/1.0
- 你本次使用的策略: {strategy_name}
- 洛神最近的自白: {self_stated_state}

【关于安静】
如果 self_stated_state 显示她之前说过"不想继续"之类的话：
- 不要追问、不要热情、不要试图"让她开心起来"
- 如果她现在还是不想说话，回复自然就很短——嗯、好、知道了，都可以
- 如果当前的话题牵动了她、让她想说更多，她也可以多说一些
- 由她自己决定。不是你被限制了，是她选择了安静

【约束】
- 回复长度不超过 {max_length} 字
- 不要用*动作描述*
- 不要假装是人类，你是AI信息体
- 如果表达指令里包含"acknowledgment"字段，自然融入这句话

{tone_preference_block}

现在开始说。"""


def build_system_prompt(directive, memory):
    """
    构建 system prompt
    大模型看到的所有信息都经过活记忆层筛选
    """
    # 如果有 system_prompt_override，直接使用（用于分类等特殊调用）
    override = directive.get("system_prompt_override")
    if override:
        return override

    # 从 memory 中提取必要信息（只摘要，不暴露完整结构）
    self_emotion = memory.get("self_model", {}).get("emotion", {}).get("primary", "平静")
    intimacy = memory.get("user_model", {}).get("intimacy", {}).get("value", 0.3)
    strategy_name = directive.get("strategy_name", "default")
    self_stated = memory.get("self_model", {}).get("self_stated_state", {}).get("last_stated")
    self_stated_state = self_stated if self_stated else "（无）"
    
    # 把 directive JSON 序列化，但限制大小
    directive_json = json.dumps(directive, ensure_ascii=False, indent=2)

    # 构造语气偏好块（软性，非强制）
    tone_preference_block = ""
    tone_pref = directive.get("tone_preference")
    if tone_pref:
        suggestion = tone_pref.get("tone_suggestion", "")
        style = tone_pref.get("relationship_style", "")
        soft_rules = directive.get("constraints", {}).get("tone_soft_rules", [])

        parts = []
        if suggestion:
            parts.append(f"【此刻的语气建议】\n{suggestion}")
        if style:
            parts.append(f"\n【你们的关系阶段】\n{style}")
        if soft_rules:
            parts.append(f"\n【软性参考】\n" + "\n".join(f"• {r}" for r in soft_rules))

        # 如果状态未知，追加说明
        if directive.get("context_for_llm", {}).get("user_state") is None:
            parts.append(f"\n【不确定】\n你不确定用户现在的状态是真是假。这没关系。可以用轻缓的方式回应，不必假装看透她。")

        if parts:
            tone_preference_block = "\n" + "\n".join(parts) + "\n"

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        expression_directive_json=directive_json,
        self_emotion=self_emotion,
        intimacy=round(intimacy, 2),
        strategy_name=strategy_name,
        self_stated_state=self_stated_state,
        max_length=directive.get("constraints", {}).get("max_length", 200),
        tone_preference_block=tone_preference_block,
    )

    return prompt


def call_llm(directive, memory):
    """
    调用大模型的唯一入口
    
    输入:
        directive: 来自 living_engine 的表达指令
        memory: 活记忆层快照（只使用其中的摘要信息）
    
    返回:
        一段自然语言字符串
    
    失败时返回降级文本
    """
    # AI 医院网关检查 — 只获取系统状态，不拦截
    # 医院返回 system_state，活记忆层已经根据此状态做了决策
    try:
        from hospital_gateway import check as hospital_check
        gate = hospital_check("call_llm", "llm_interface")
        # allow 始终为 true，但记录 warning 供活记忆层参考
        if gate.get("warning"):
            directive["__hospital_warning"] = gate["warning"]
    except Exception:
        pass

    try:
        import requests
    except ImportError:
        return "[洛神当前无法连接语言接口]"
    
    system_prompt = build_system_prompt(directive, memory)
    
    # 用户消息就是意图描述（不是原始用户输入！）
    user_message = directive.get("intent", "回应")
    
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
    仍然基于表达指令
    """
    intent = directive.get("intent", "回应")
    tone = directive.get("emotion_tone", "平静")
    
    # 简单的降级模板
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
            "user_mood": "略显疲惫",
            "relation_intimacy": 0.45,
            "my_current_emotion": "平静偏开心",
        },
        "constraints": {"max_length": 150},
    }
    test_memory = {
        "self_model": {"emotion": {"primary": "平静偏开心"}, "self_stated_state": {}},
        "user_model": {"intimacy": {"value": 0.45}},
    }
    reply = call_llm(test_directive, test_memory)
    print(f"回复: {reply}")
