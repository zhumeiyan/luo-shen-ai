#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 汉字字源预处理模块 hanzi_etymology_preprocess.py"""
import hashlib
import json
import os
import time

CHARS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
         "空", "轻", "今", "静", "满", "贵", "久", "紧", "闲", "息",
         "流", "转", "升", "降", "多", "少", "中", "高", "低", "明"]

SYSTEM_PROMPT = (
    "你是汉字字源专家。请根据《说文解字》和古文字演变，为给定的汉字生成以下字段："
    "char（汉字）、ancient（古文本义，用简洁文言解释）、modern（现代白话含义）、"
    "evolution（甲骨文到简体的演变简述，字数不超过30字）。"
    "输出必须是JSON对象，不要添加任何额外文字。"
)


def query_llm(url, api_key, model, char):
    import living_engine
    _r = living_engine.generate_response(char, source="hanzi_etymology_preprocess",
                                         extra_context=SYSTEM_PROMPT)
    content = _r["reply"]
    if not content or content.startswith("[洛神"):
        raise ValueError("LLM call blocked or error")
    # 提取 JSON 对象
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object in response")
    return json.loads(content[start:end + 1])


def main():
    try:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL", "glm-4-flash")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        entries = {}
        for char in CHARS:
            try:
                info = query_llm(api_url, api_key, model, char)
                entries[char] = {
                    "ancient": info.get("ancient", ""),
                    "modern": info.get("modern", ""),
                    "evolution": info.get("evolution", ""),
                }
            except Exception as e:
                print(json.dumps({"error": "request failed for " + char + ": " + str(e)}))

        output = {
            "schema_version": 1,
            "module": "hanzi_knowledge_base",
            "version": 1,
            "description": "洛神可读的汉字字源知识库，由大模型预处理生成。",
            "entries": entries,
        }

        with open('hanzi_knowledge_base.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(output, ensure_ascii=False, indent=2) + '\n')

        with open('hanzi_knowledge_base.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        records_chain = [json.loads(ln) for ln in chain_lines]
        prev_hash = records_chain[-1].get("record_hash") if records_chain else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "hanzi_knowledge_base.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        with open('hanzi_knowledge_base.json', 'r', encoding='utf-8') as f:
            print(f.read(), end="")
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
