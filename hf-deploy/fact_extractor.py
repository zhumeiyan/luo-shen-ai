#!/usr/bin/env python3
"""
最小事实提取模块
从用户输入中提取个人事实，写入活记忆层的 known_facts。

设计原则：
- 确定性规则，不依赖 LLM
- 只提取事实类信息（地点、偏好、恐惧、计划、人物、日期）
- 不提取情绪、不生成总结
- 写入后落链
"""
import json
import os
import sys
import re
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import living_engine


# ── 提取规则（按顺序应用）──────────────────────────────

def _extract_relocation(text):
    """我要离开XX / 我下个月去XX / 我搬到XX"""
    patterns = [
        r"(?:我要|我准备|我计划|我即将|我下个月|明年|明天)?[\s]*(?:离开|搬去|搬到|移居|移民)[\s]*([\u4e00-\u9fa5]{2,8}(?:市|省|国|洲)?)",
        r"([\u4e00-\u9fa5]{2,8})(?:我)?(?:要|准备|计划)?离开",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return {"type": "relocation", "fact": f"要离开{m.group(1)}", "target": m.group(1)}
    return None


def _extract_location(text):
    """我在XX / 我住在XX / 我来自XX"""
    patterns = [
        r"(?:我住在|我来自|我在|我家在|我目前待在)([\u4e00-\u9fa5]{2,8})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return {"type": "location", "fact": f"住在{m.group(1)}", "target": m.group(1)}
    return None


def _extract_fear(text):
    """我怕XX / 我害怕XX / 我恐惧XX / 我一个人"""
    patterns = [
        r"我(?:其实|真的)?(?:好|很|特别)?(?:怕|害怕|恐惧|畏惧)([\u4e00-\u9fa5]{2,12})",
        r"我(?:真的|好|很|特别|就是|实在)?(?:怕|害怕)([\u4e00-\u9fa5]{2,12})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            target = m.group(1).strip()
            if len(target) >= 2:
                return {"type": "fear", "fact": f"害怕{target}", "target": target}
    if re.search(r"我怕一个人|我一个人好怕|我不敢一个人|我一个人在家很怕", text):
        return {"type": "fear", "fact": "害怕一个人待着", "target": "一个人"}
    if re.search(r"我害怕一个人|我很怕一个人", text):
        return {"type": "fear", "fact": "害怕一个人待着", "target": "一个人"}
    return None


def _extract_dislike(text):
    """我不爱吃XX / 我不喜欢XX / 我讨厌XX"""
    patterns = [
        r"我(?:一直|从小|从来|真的|就是|一直)?(?:不怎么|不太|不|不爱|不喜欢|讨厌|嫌弃)(?:吃|喝|喜欢|爱)([\u4e00-\u9fa5]{2,8})",
        r"我(?:不吃|不喝|不吃|不爱吃|不喜欢吃|讨厌吃)([\u4e00-\u9fa5]{2,8})",
        r"([\u4e00-\u9fa5]{2,8})(?:不合我的口味|不合我胃口|我受不了)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            target = m.group(1).strip()
            if len(target) >= 2:
                return {"type": "food_dislike", "fact": f"不喜欢{target}", "target": target}
    return None


def _extract_preference(text):
    """我喜欢XX"""
    patterns = [
        r"我(?:其实|一直|真的|好|很|特别)?(?:喜欢|爱|热爱)([\u4e00-\u9fa5]{2,12})(?:啊|呢|呀|的)?$",
        r"我(?:其实|一直|真的|好|很|特别)?(?:喜欢|爱|热爱)([\u4e00-\u9fa5]{2,12})(?!的)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            target = m.group(1).strip()
            if len(target) >= 2:
                return {"type": "preference", "fact": f"喜欢{target}", "target": target}
    return None


def _extract_learning(text):
    """我在学XX / 我开始学XX / 我正在学XX"""
    patterns = [
        r"我(?:最近|现在|刚开始|开始|正在|打算)?在?(?:学|学习|练习)([\u4e00-\u9fa5]{2,10})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            target = m.group(1).strip()
            if len(target) >= 2:
                return {"type": "learning", "fact": f"在学习{target}", "target": target}
    return None


def _extract_person(text):
    """我妈XX / 我爸XX / 我老公XX / 我男朋友XX / 我女朋友XX"""
    patterns = [
        r"(我妈|我爸|我老公|我老婆|我男朋友|我女朋友|我闺蜜|我哥们|我朋友|我姐|我哥|我妹|我弟)([\u4e00-\u9fa5]{2,6})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return {"type": "person_mention", "fact": f"提到{m.group(1)}: {m.group(2)}", "role": m.group(1), "detail": m.group(2)}
    return None


def _extract_dream(text):
    """我梦到XX / 我梦见XX"""
    patterns = [
        r"我(?:昨晚|昨天|今天|刚刚|昨天半夜)?(?:梦到|梦见)([\u4e00-\u9fa5]{2,12})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return {"type": "dream", "fact": f"梦到{m.group(1)}", "target": m.group(1)}
    return None


def _extract_plan(text):
    """我下个月XX / 我明天XX / 我下周XX"""
    patterns = [
        r"我(?:下个月|下周|明天|后天|这个月|今年)([\u4e00-\u9fa5]{2,10})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return {"type": "plan", "fact": f"计划: 下个月{m.group(1)}", "when": m.group(0)[:4], "what": m.group(1)}
    return None


def _extract_food_habit(text):
    """我从小就不爱吃XX / 我从来不吃XX"""
    patterns = [
        r"我(?:从小|从来|一直|真的)?(?:就|都)?(?:不吃|不爱吃|不喜欢吃|嫌弃)([\u4e00-\u9fa5]{2,8})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return {"type": "food_dislike", "fact": f"不爱吃{m.group(1)}", "target": m.group(1)}
    return None


# ── 提取器函数 ────────────────────────────────────────

ALL_EXTRACTORS = [
    _extract_relocation,
    _extract_location,
    _extract_fear,
    _extract_food_habit,
    _extract_dislike,
    _extract_dream,
    _extract_preference,
    _extract_learning,
    _extract_person,
    _extract_plan,
]


def extract_facts(text):
    """
    从用户输入文本中提取所有匹配的个人事实。
    返回 list of {"type", "fact", ...}
    """
    results = []
    seen_facts = set()
    for ext in ALL_EXTRACTORS:
        r = ext(text)
        if r and r["fact"] not in seen_facts:
            results.append(r)
            seen_facts.add(r["fact"])
    return results


def save_facts_to_memory(facts, memory):
    """
    将提取的事实写入 memory["user_model"]["known_facts"]。
    结构: {"facts": [{"type", "fact", "target", ...}], "last_updated": timestamp}
    """
    if not facts:
        return memory
    
    existing = memory.get("user_model", {}).get("known_facts", {})
    if not isinstance(existing, dict):
        existing = {}
    existing_facts = existing.get("facts", [])
    
    # 去重
    seen = {f["fact"] for f in existing_facts}
    added = []
    for f in facts:
        if f["fact"] not in seen:
            f["recorded_at"] = time.time()
            existing_facts.append(f)
            seen.add(f["fact"])
            added.append(f)
    
    memory.setdefault("user_model", {})["known_facts"] = {
        "facts": existing_facts,
        "last_updated": time.time(),
        "added_this_round": added,
    }
    return memory


def extract_and_save(user_input, memory=None):
    """
    主入口：提取 + 保存 + 落链。
    返回 (facts_list, memory)
    """
    if memory is None:
        memory = living_engine._load_json("active_memory/active_memory.json")
    
    facts = extract_facts(user_input)
    if facts:
        memory = save_facts_to_memory(facts, memory)
        living_engine._save_json_atomic("active_memory/active_memory.json", memory)
        living_engine.append_hash_chain("hash_chain_v2.log", "active_memory/active_memory.json")
    
    return facts, memory
