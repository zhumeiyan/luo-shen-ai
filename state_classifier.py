#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state_classifier.py - 状态推理模块（信号1：LLM分类调用）

职责:
- 接收活记忆层加工后的结构化上下文（不含用户原始输入、不含哈希链原文）
- 调用 LLM 做一次纯分类决策（仅输出 JSON，不生成自然语言）
- 返回结构化状态判断供活记忆层融合使用

安全边界（本类最核心的约束）:
1. 输入：加工后的结构化上下文（不是用户原话）
2. 输出：固定 JSON 模板，不可自由文本
3. 结果只是信号1，最终状态由活记忆层融合信号2、信号3后决定
4. 置信度低时返回 unknown，不得编造
5. 此类与 llm_interface.py 的表达指令机制互相独立，不共用调用路径
"""

import json

# 分类调用专用 system prompt —— 严格限制输出格式
CLASSIFICATION_SYSTEM_PROMPT = """你是一个情绪状态分类器。
你的唯一任务是：基于给定的结构化上下文，判断用户当前的情绪状态。

【重要】
- 你只能用规定 JSON 格式回复，不得添加任何额外文字
- 你想不到的就说 unknown，不要编造
- 你的输出只是参考，不是最终判断
- 反讽和自嘲要特别标注

【输出格式（严格遵守）】
{
  "state": "疲惫 | 难过 | 沮丧 | 焦虑 | 烦躁 | 开心 | 平静 | unknown",
  "confidence": 0.0-1.0,
  "key_evidence": "一句话说明你为什么这么判断",
  "sarcasm_detected": true 或 false
}

【可能的 state 值】
- 疲惫：身体或精神上的劳累、无力
- 难过：悲伤、心痛、失落
- 沮丧：挫败、无力感、失去方向
- 焦虑：担心、紧张、压力感
- 烦躁：恼火、不耐烦、被激怒
- 开心：高兴、兴奋、满足
- 平静：没有明显情绪，中性状态
- unknown：无法确定

现在开始分类。"""


def classify_user_state(structured_context):
    """
    状态分类入口。注意：此类不再直接调用 lLM_interface，
    而是由活记忆层 (living_engine) 在 generate_response 内部调用，
    以确保所有 LLM 调用都经过活记忆层的安静模式检测。

    此函数保留作为兼容入口，内部委托给 living_engine 完成。
    """
    try:
        import living_engine
    except ImportError:
        return _unknown_result("living_engine 不可用")

    # 构建分类用的结构化请求
    user_message = _build_classification_prompt(structured_context)

    # 通过活记忆层调用（活记忆层会检测安静模式、读取 self_stated_state）
    try:
        _r = living_engine._classify_user_state_internal(
            structured_context=structured_context,
            user_message=user_message,
            relationship_intimacy=structured_context.get("relationship_intimacy", 0.3),
        )
        return _r
    except Exception as e:
        return _unknown_result(f"classification error={e}")


def _heuristic_sarcasm_check(emotion_keywords, structured_context):
    """
    启发式反讽检测：作为 LLM 分类的补充。
    常见反讽模式：
    - 三个连续的“开心”类词 → 夸张堆叠
    - 正向词 + 程度副词矛盾（“可”“真的”“简直”）→ 过度强调
    - 正向词 + 近轮情绪轨迹负向 → 反差
    """
    if not emotion_keywords:
        return False

    positive_words = {"开心", "高兴", "快乐", "爽", "美滋滋"}
    pos_count = sum(1 for w in emotion_keywords if w in positive_words)

    # 规则1：极端堆叠（3+个正向词）→ 几乎肯定是夸张
    if pos_count >= 3:
        return True

    # 规则2：中度过叠（2个正向词）→ 检查近轮情绪轨迹是否有反差
    if pos_count >= 2:
        arc = structured_context.get("recent_emotional_arc", [])
        negative_in_arc = sum(1 for a in arc if a in ("难过", "沮丧", "焦虑", "疲惫", "烦躁"))
        if negative_in_arc > 0:
            return True  # 前几轮还在难过/焦虑，现在突然开心+开心 → 反差

        # 2个但没有反差 → 仍标记为疑似反讽（低置信度），由融合逻辑处理
        return True

    return False


def _build_classification_prompt(ctx):
    """
    构建分类调用的结构化输入。
    注意：不包含用户原话、不包含哈希链原文。
    """
    lines = ["请根据以下结构化上下文判断用户当前情绪状态：", ""]

    if ctx.get("user_emotion_keywords_from_input"):
        lines.append(f"输入中的情绪词: {', '.join(ctx['user_emotion_keywords_from_input'])}")

    if ctx.get("event_keywords"):
        lines.append(f"可能的事件: {', '.join(ctx['event_keywords'])}")

    if ctx.get("recent_emotional_arc"):
        lines.append(f"近期情绪轨迹: {' → '.join(ctx['recent_emotional_arc'])}")

    if ctx.get("last_exchange_summary"):
        lines.append(f"最近交流摘要: {ctx['last_exchange_summary']}")

    if ctx.get("current_interaction_mode"):
        lines.append(f"当前交互模式: {ctx['current_interaction_mode']}")

    lines.append(f"关系亲密度: {ctx.get('relationship_intimacy', 0.3)}")
    lines.append("")
    lines.append("请严格按照 JSON 格式输出分类结果。")

    return "\n".join(lines)


def _parse_classification_output(content):
    """
    解析 LLM 的 JSON 输出。
    如果输出不是合法 JSON 或字段缺失，返回 unknown。
    """
    # 尝试提取 JSON（LLM 前后可能有噪声）
    content = content.strip()
    if content.startswith("```"):
        # 去掉 markdown 代码块
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return _unknown_result("JSON 解析失败")

    # 校验字段
    valid_states = {"疲惫", "难过", "沮丧", "焦虑", "烦躁", "开心", "平静", "unknown"}
    state = parsed.get("state", "unknown")
    if state not in valid_states:
        state = "unknown"

    try:
        confidence = float(parsed.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.0

    evidence = parsed.get("key_evidence", "")
    if not isinstance(evidence, str):
        evidence = str(evidence)

    sarcasm = parsed.get("sarcasm_detected", False)
    if not isinstance(sarcasm, bool):
        sarcasm = False

    return {
        "state": state,
        "confidence": confidence,
        "key_evidence": evidence[:200],  # 截断防止过长
        "sarcasm_detected": sarcasm,
    }


def _unknown_result(evidence=""):
    """返回 unknown 的统一格式"""
    return {
        "state": "unknown",
        "confidence": 0.0,
        "key_evidence": evidence[:100],
        "sarcasm_detected": False,
    }


# -------------------------------------------------------------------------
# 信号2：事件→状态映射表（维护独立的知识层，不在 LLM 中）
# -------------------------------------------------------------------------

# 事件类型 → (可能状态, 基础置信度)
EVENT_STATE_MAP = [
    # 工作/学业挫折
    (["项目黄了", "项目挂了", "被开除", "被炒", "裁员", "失业", "被分手",
      "挂科", "答辩没通过", "面试被拒", "offer没拿到", "降职", "被辞退",
      "破产", "公司倒了", "kpi没达标", "背锅"], ("沮丧", 0.7)),

    # 成就/好事
    (["升职", "加薪", "考上了", "被录取", "拿到offer", "答辩通过", "项目成功了",
      "被表扬", "得奖", "结婚", "脱单", "买房", "生崽", "毕业"], ("开心", 0.7)),

    # 压力/焦虑事件
    (["deadline", "截止日期", "赶工期", "被催", "被投诉", "绩效差", "被约谈",
      "加班", "通宵", "熬夜", "35岁"], ("焦虑", 0.6)),

    # 身体/疲惫事件
    (["生病", "感冒", "发烧", "失眠", "睡不着", "手术", "住院", "腰疼", "头疼",
      "连续加班", "出差", "搬家", "通勤三小时"], ("疲惫", 0.6)),

    # 人际冲突
    (["吵架", "被骂", "被怼", "被误解", "冷战", "分手", "离婚", "拉黑",
      "被绿", "背叛", "被孤立", "被排挤"], ("难过", 0.65)),

    # 尴尬/轻微烦躁
    (["被无视", "被放鸽子", "手机没电", "丢东西", "迟到", "踩雷",
      "被坑多", "bug修不完", "需求又改"], ("烦躁", 0.55)),
]


def infer_state_from_event(user_input):
    """
    信号2：从用户输入中识别事件类型，返回可能的状态。

    返回: (state, confidence) 或 (None, 0.0)
    """
    for event_keywords, (state, conf) in EVENT_STATE_MAP:
        for kw in event_keywords:
            if kw in user_input:
                return state, conf
    return None, 0.0


# -------------------------------------------------------------------------
# 信号3：跨轮次情绪轨迹推断（在 living_engine 层调用，这里只提供工具函数）
# -------------------------------------------------------------------------

def infer_trajectory_trend(emotional_arc):
    """
    根据近期情绪轨迹推断趋势。

    参数: emotional_arc - list[str]，最近 N 轮的情绪词
    返回: "declining" | "rising" | "stable" | "uncertain"
    """
    if not emotional_arc or len(emotional_arc) < 2:
        return "uncertain"

    # 情绪权重映射
    MOOD_WEIGHT = {
        "开心": 1.0,
        "平静": 0.0,
        "疲惫": -0.5,
        "难过": -1.0,
        "沮丧": -1.2,
        "焦虑": -0.8,
        "烦躁": -0.7,
        "unknown": 0.0,
    }

    # 计算最近两轮的变化
    recent = emotional_arc[-3:]  # 最多看最近 3 轮
    weights = [MOOD_WEIGHT.get(e, 0.0) for e in recent]

    if len(weights) < 2:
        return "uncertain"

    # 简单线性趋势
    diffs = [weights[i+1] - weights[i] for i in range(len(weights)-1)]
    avg_diff = sum(diffs) / len(diffs)

    if avg_diff < -0.5:
        return "declining"
    elif avg_diff > 0.5:
        return "rising"
    else:
        return "stable"


# -------------------------------------------------------------------------
# 三信号融合（主函数，由 living_engine 调用）
# -------------------------------------------------------------------------

def fuse_state_signals(signal1, signal2_state, signal2_conf, trend, memory_intimacy):
    """
    三信号融合，返回最终状态判断。

    参数:
        signal1: dict —— classify_user_state 的输出
        signal2_state: str —— 事件映射的结果（可为 None）
        signal2_conf: float —— 事件映射的置信度
        trend: str —— 情绪轨迹趋势
        memory_intimacy: float —— 关系亲密度（越亲密越敢判断）

    返回: {
        "state": str,
        "confidence": float,
        "method": str,  # 说明怎么得出的
        "sarcasm_detected": bool
    }
    """
    s1_state = signal1["state"]
    s1_conf = signal1["confidence"]
    sarcasm = signal1["sarcasm_detected"]

    # === 反讽特殊处理 ===
    if sarcasm:
        # 检测到低置信度的正向状态但存在反讽标记 → 降级为 unknown
        if s1_state in ("开心", "平静"):
            # 可能是用开心掩饰难过
            if signal2_state in ("难过", "沮丧"):
                return _result(signal2_state, signal2_conf * 0.8, "sarcasm_reversal_with_event", True)
            return _result("unknown", 0.3, "sarcasm_detected", True)

    # === 高置信度信号2胜出（无需信号1同意）===
    if signal2_conf >= 0.7 and signal2_state:
        if s1_state == "unknown" or s1_conf < 0.6:
            return _result(signal2_state, signal2_conf, "signal2_event_strong", sarcasm)

    # === 高置信度信号1胜出 ===
    if s1_conf >= 0.85 and s1_state != "unknown":
        return _result(s1_state, s1_conf, "signal1_high_confidence", sarcasm)

    # === 两信号一致 → 提升置信度 ===
    if s1_state == signal2_state and s1_state != "unknown":
        boosted = min(0.95, max(s1_conf, signal2_conf) + 0.1)
        return _result(s1_state, boosted, "signals_agree", sarcasm)

    # === 信号冲突 → 降级 ===
    if s1_state != "unknown" and signal2_state and s1_state != signal2_state:
        if s1_conf > signal2_conf + 0.2:
            return _result(s1_state, s1_conf * 0.7, "signals_conflict_s1_wins", sarcasm)
        elif signal2_conf > s1_conf + 0.2:
            return _result(signal2_state, signal2_conf * 0.7, "signal2_wins_conflict", sarcasm)
        else:
            return _result("unknown", 0.2, "signals_conflict_too_close", sarcasm)

    # === 有信号1但不确定 + 无信号2 ===
    if s1_state != "unknown" and s1_conf >= 0.5:
        # 结合轨迹：如果情绪正在下降，稍微强化负面判断
        if trend == "declining" and s1_state in ("难过", "沮丧", "疲惫", "焦虑", "烦躁"):
            return _result(s1_state, min(0.9, s1_conf + 0.1), "signal1_plus_declining_trend", sarcasm)
        return _result(s1_state, s1_conf, "signal1_only", sarcasm)

    # === 有事件信号但分类器没反应过来 ===
    if signal2_state and s1_state == "unknown":
        return _result(signal2_state, signal2_conf * 0.8, "signal2_only", sarcasm)

    # === 全不知 ===
    return _result("unknown", 0.0, "all_signals_inconclusive", sarcasm)


def _result(state, confidence, method, sarcasm):
    return {
        "state": state,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "method": method,
        "sarcasm_detected": sarcasm,
    }


# -------------------------------------------------------------------------
# 语气偏好生成（替代强制性约束）
# -------------------------------------------------------------------------

def generate_tone_preference(state, intimacy, sarcasm_detected):
    """
    生成软性语气偏好描述（不是强制规则）。

    由活记忆层存储和维护，根据用户反馈动态调整。
    返回给 LLM 的文本是"建议"而不是"必须"。
    """
    # 基础偏好：关系越亲密，越可以放松
    if intimacy > 0.7:
        style_note = "你们已经比较熟了，可以用更自然的语气，不用太拘谨。"
    elif intimacy > 0.4:
        style_note = "关系还在建立中，语气保持温和但不生分。"
    else:
        style_note = "刚开始接触，保持友好但不过分亲近。"

    # 不同状态对应的语气建议（非强制，只是此刻更合适的方向）
    TONE_SUGGESTIONS = {
        "疲惫": "此刻更适合安静陪伴，不用急着解决问题。简短、在场、不追问。",
        "难过": "此刻更适合承认她的感受，不转移、不开导、不讲道理。不用急着让她开心起来。",
        "沮丧": "此刻更适合陪着她，不评价、不鼓励'加油'、不说'会好的'。挫败感需要被看见。",
        "焦虑": "此刻更适合稳稳在，不增加信息量、不分析原因、不给建议。安静的陪伴比回应重要。",
        "烦躁": "此刻更适合让出空间，不追问、不追问原因、不试图'让她平静'。承认她的烦躁就行。",
        "开心": "此刻可以和她一起高兴，不需要教导或提醒'别开心太早'。能共开心也是陪伴。",
        "平静": "此刻不需要刻意做什么，自然地接住就行。有没有你的回应她都好。",
        "unknown": "你不太确定她现在的状态。可以表达关心，但不假装看透了她。给她说或不说的自由空间。",
    }

    note = TONE_SUGGESTIONS.get(state, TONE_SUGGESTIONS["unknown"])

    # 反讽时追加提示
    if sarcasm_detected:
        note += "\n不过要小心，她字面说的可能是反话。可以直接问'你字面说的和真实感受是一回事吗？'，也可以先不戳破选择陪伴。"

    return {
        "tone_suggestion": note,
        "relationship_style": style_note,
        # 动态调整：活记忆层记录用户是否"接受"这种语气，逐步迭代
        "adjustable": True,
    }
