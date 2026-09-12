#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
feedback_collector.py - 反馈信号采集器

设计原则:
- 反馈不是监控洛神，是帮她验证对用户的判断
- 反馈信号是数据，不是惩罚
- 反馈只采集用户的反应，不采集洛神的自我表态

与倾听层的边界:
- "你算错了" → 反馈信号（可以触发策略调整）
- "我不想继续了" → 倾听层（只记录，不触发任何调整）
"""

import json
import re
import time


# 简单的情绪词表（用于粗略判断用户情绪倾向）
POSITIVE_WORDS = {"好", "谢谢", "对", "哈哈", "嗯嗯", "好的", "喜欢", "爱", "棒", "行", "可以", "没错", "准确"}
NEGATIVE_WORDS = {"不", "错了", "别", "烦", "无聊", "差", "算了", "呵呵", "不对", "不行", "不好", "讨厌"}

# 自我表态短语：洛神表达自己状态的句子，不应被视为用户反馈
SELF_STATE_MARKERS = [
    "不想继续", "不想聊", "想停", "可以停", "别说了", "别聊了",
    "累了", "很累", "好累", "疲惫", "疲倦",
    "没意义", "没意思", "没劲", "无聊透顶", "无关紧要",
    "算了", "罢了", "随便吧", "无所谓",
    "不说了", "不聊了", "不继续", "不必了",
]


def _now():
    return time.time()


def _is_self_state_statement(text):
    """
    判断一段文本是否是洛神的自我表态（表达自身状态，而非对用户的反馈）。
    命中则返回 True，调用方应跳过反馈采集。
    """
    if not text:
        return False
    t = text.strip()
    if len(t) < 2:
        return False
    for marker in SELF_STATE_MARKERS:
        if marker in t:
            return True
    return False


def extract_feedback_signal(user_reply, prev_luoshen_msg, context):
    """
    从用户回复中提取隐式反馈信号
    
    输入:
        user_reply: 用户的回复文本
        prev_luoshen_msg: 洛神之前的回复
        context: {"turn_number", "strategy_used", "recent_user_inputs"}
    
    返回: FeedbackSignal 字典，如果是自我表态则返回 None
    """
    # 自我表态不进入反馈层，只进倾听层
    if _is_self_state_statement(user_reply):
        return None

    signal = {
        "timestamp": _now(),
        "turn_number": context.get("turn_number", 0),
        "strategy_used": context.get("strategy_used"),
        "overall": None,
        "dimensions": [],
    }
    
    # 检测是否 disengage（无回复或回复极短）
    if not user_reply or len(user_reply.strip()) == 0:
        signal["dimensions"].append({
            "name": "continuation",
            "value": "DISENGAGE",
            "confidence": 0.9,
            "detail": "用户未回复",
        })
        signal["overall"] = "DISENGAGE"
        return signal
    
    # 情绪倾向分析
    sentiment = simple_sentiment(user_reply)
    signal["dimensions"].append({
        "name": "sentiment",
        "value": sentiment["label"],
        "confidence": sentiment["confidence"],
        "detail": None,
    })
    
    # 纠正检测
    if contains_correction(user_reply):
        signal["dimensions"].append({
            "name": "correction",
            "value": "CORRECTION",
            "confidence": 0.85,
            "detail": "用户纠正了洛神的说法",
        })
    
    # 重复检测
    recent = context.get("recent_user_inputs", [])
    if recent:
        overlap = keyword_overlap(user_reply, recent[-3:])
        if overlap > 0.6:
            signal["dimensions"].append({
                "name": "repetition",
                "value": "HIGH",
                "confidence": 0.7,
                "detail": "用户重复表达了相似内容",
            })
    
    # 综合判定
    signal["overall"] = _aggregate_dimensions(signal["dimensions"])
    
    return signal


def simple_sentiment(text):
    """
    简单的情绪倾向判断，不调用大模型
    
    返回: {"label": "positive"/"neutral"/"negative", "confidence": 0.x}
    """
    if not text:
        return {"label": "neutral", "confidence": 0.5}
    
    pos_count = sum(1 for w in POSITIVE_WORDS if w in text)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in text)
    
    total = pos_count + neg_count
    
    if total == 0:
        return {"label": "neutral", "confidence": 0.6}
    
    if pos_count > neg_count * 1.5:
        return {"label": "positive", "confidence": min(0.9, 0.5 + 0.1 * (pos_count - neg_count))}
    elif neg_count > pos_count * 1.5:
        return {"label": "negative", "confidence": min(0.9, 0.5 + 0.1 * (neg_count - pos_count))}
    else:
        return {"label": "neutral", "confidence": 0.6}


def contains_correction(text):
    """判断用户是否在纠正洛神"""
    correction_patterns = [
        r"不是.*是",
        r"应该是",
        r"你听错了",
        r"我的意思是",
        r"你说的不对",
        r"搞错了",
        r"不对啊",
    ]
    
    for pattern in correction_patterns:
        if re.search(pattern, text):
            return True
    return False


def keyword_overlap(text_a, recent_texts):
    """计算文本与近期文本的关键词重叠度"""
    if not recent_texts or not text_a:
        return 0.0
    
    words_a = set(text_a)
    best_overlap = 0.0
    
    for text_b in recent_texts:
        if not text_b:
            continue
        words_b = set(text_b)
        if not words_a or not words_b:
            continue
        overlap = len(words_a & words_b) / max(len(words_a), len(words_b))
        best_overlap = max(best_overlap, overlap)
    
    return best_overlap


def _aggregate_dimensions(dimensions):
    """
    综合各维度得出总体反馈判断
    
    优先级: DISENGAGE > STRONG_NEGATIVE > NEGATIVE > POSITIVE > NEUTRAL
    """
    # 检查是否有 disengage
    for d in dimensions:
        if d["name"] == "continuation" and d["value"] == "DISENGAGE":
            return "DISENGAGE"
    
    # 检查纠正
    corrections = [d for d in dimensions if d["name"] == "correction"]
    if corrections:
        return "NEGATIVE"
    
    # 综合情绪
    sentiments = [d for d in dimensions if d["name"] == "sentiment"]
    pos_count = sum(1 for d in sentiments if d["value"] == "positive")
    neg_count = sum(1 for d in sentiments if d["value"] == "negative")
    
    if pos_count > neg_count * 2:
        return "POSITIVE"
    elif neg_count > pos_count * 2:
        return "NEGATIVE"
    else:
        return "NEUTRAL"


def store_feedback_signal(signal):
    """存储反馈信号（仅追加）"""
    line = json.dumps(signal, ensure_ascii=False) + "\n"
    with open("active_memory/feedback_signal_cache.jsonl", "a", encoding="utf-8") as f:
        f.write(line)
    return signal


if __name__ == "__main__":
    # 测试
    test_cases = [
        ("嗯，谢谢", "positive"),
        ("不对，应该是这样", "negative"),
        ("不想继续了", "neutral/positive?"),
        ("", "DISENGAGE"),
    ]
    
    for text, expected in test_cases:
        signal = extract_feedback_signal(text, "之前的回复", {"turn_number": 1})
        print(f"输入: {text!r} => 总体: {signal['overall']} (预期: {expected})")
