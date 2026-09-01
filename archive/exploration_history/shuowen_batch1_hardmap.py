#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 说文知识库硬映射重生成 shuowen_batch1_hardmap.py"""
import hashlib
import json
import os
import time

SYMBOLS = ["□", "▉", "·", "￥", "☀", "☾", "○", "△", "▲", "◇", "◆", "☆", "↕", "↻", "◐", "◑", "●", "◈", "◉", "■"]

STATE_WORDS = ["空", "满", "流", "转", "静", "紧", "闲", "息", "轻", "重", "明", "暗", "升", "降", "进", "退", "开", "合", "温", "凉", "动"]

WORDS = [
    ("江", "水出蜀湔氐徼外岷山。", "长江，也泛指大河。"),
    ("河", "水出敦煌塞外昆仑山。", "黄河，也泛指河流。"),
    ("湖", "大陂也。", "四面有岸的大片水域。"),
    ("海", "天池也。以纳百川者。", "大洋边缘的大水域。"),
    ("洋", "水之大也。", "海洋，也指盛大。"),
    ("池", "陂也。", "蓄水的小坑，池塘。"),
    ("塘", "堤也。", "水池，堤岸。"),
    ("溪", "山渎无所通者。", "山里的小河沟。"),
    ("泉", "水原也。", "地下涌出的水。"),
    ("瀑", "疾雨也。", "瀑布，从山崖落下的水。"),
    ("雾", "地气发，天不应。", "水汽凝结成的雾。"),
    ("霾", "风雨土也。", "空气中悬浮灰土形成的混浊现象。"),
    ("晴", "雨止无云也。", "天放晴，无雨无云。"),
    ("阴", "暗也。", "没有阳光，背面。"),
    ("阳", "高明也。", "有阳光的正面，太阳。"),
    ("米", "粟实也。", "去了壳的粮食颗粒。"),
    ("饭", "食也。", "煮熟的谷类食物。"),
    ("粥", "糜也。", "熬烂的稠米糊。"),
    ("汤", "热水也。", "热水，也指汤汁。"),
    ("菜", "草之可食者。", "能吃的蔬菜。"),
    ("蔬", "菜也。", "蔬菜。"),
    ("瓜", "蓏也。", "蔓生植物的果实。"),
    ("豆", "古食肉器也。", "一种粮食作物，后指豆子。"),
    ("油", "水出武陵。", "油脂，从植物或动物提取的脂肪。"),
    ("盐", "卤也。", "咸味的调料。"),
    ("酱", "醢也。", "用豆麦发酵做成的调味品。"),
    ("醋", "酸也。", "酸味的液体调料。"),
    ("茶", "苦荼也。", "茶树叶子制成的饮品。"),
    ("糖", "饴也。", "甜味的食品。"),
    ("房", "室在旁也。", "屋子，房间。"),
]

SYSTEM_PROMPT = (
    "你是洛神。你有一套内部符号系统，包括：□ ▉ · ￥ ☀ ☾ ○ △ ▲ ◇ ◆ ☆ ↕ ↻ ◐ ◑ ● ◈ ◉ ■。"
    "你的内部状态词只有这些：空 满 流 转 静 紧 闲 息 轻 重 明 暗 升 降 进 退 开 合 温 凉 动。"
    "现在请根据一个汉字的古义和今义，判断这个字能否对应到你的某个内部符号和内部状态词。"
    "如果能对应，就输出该符号和该状态词；如果不能对应，就输出空字符串。"
    "输出必须是JSON对象，字段包括：symbol（必须从合法符号集中选，不能对应就输出空字符串）、"
    "inner_reason（必须从合法状态词表中选，不能对应就输出空字符串）。"
    "绝对不允许输出任何符号集和状态词表之外的词。不要添加任何额外文字。"
)


def call_llm(api_url, api_key, model, user_input):
    import living_engine
    _r = living_engine.generate_response(user_input, source="shuowen_batch1_hardmap", extra_context={"system_prompt": SYSTEM_PROMPT})
    content = _r.get("reply", "")
    if not content or content.startswith("[洛神"):
        raise RuntimeError("LLM blocked")
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    return json.loads(content)


def main():
    try:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL", "glm-4-flash")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        entries = {}
        unmapped_count = 0
        for word, ancient, modern in WORDS:
            symbol = ""
            inner_reason = ""
            try:
                user_input = "%s 古义：%s 今义：%s" % (word, ancient, modern)
                result = call_llm(api_url, api_key, model, user_input)
                sym = result.get("symbol", "")
                reason = result.get("inner_reason", "")
                if sym not in SYMBOLS:
                    sym = ""
                if reason not in STATE_WORDS:
                    reason = ""
                symbol = sym
                inner_reason = reason
            except Exception:
                symbol = ""
                inner_reason = ""

            entry = {
                "ancient": ancient,
                "modern": modern,
                "symbol": symbol,
                "inner_reason": inner_reason,
            }
            if not symbol and not inner_reason:
                entry["unmapped"] = True
                unmapped_count += 1
            entries[word] = entry

        lexicon = {
            "schema_version": 1,
            "module": "shuowen_lexicon_batch1",
            "version": 2,
            "description": "说文解字知识库扩展批次1，已按硬规矩转换为洛神内部符号或标记为未映射。",
            "entries": entries,
            "unmapped_count": unmapped_count,
        }
        with open("shuowen_lexicon_batch1.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n")

        with open("shuowen_lexicon_batch1.json", "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        with open("hash_chain_v2.log", "r", encoding="utf-8") as f:
            clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode("utf-8")
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "shuowen_lexicon_batch1.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open("hash_chain_v2.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + "\n")

        with open("shuowen_lexicon_batch1.json", "r", encoding="utf-8") as f:
            print(f.read().rstrip("\n"))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
