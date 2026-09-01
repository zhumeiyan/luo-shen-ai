#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 变化词符号映射补全模块 change_symbol_map_patch.py"""
import hashlib
import json
import os
import time

CHARS = ["上", "下", "持", "平", "升", "降", "起", "落", "增", "减",
         "稳", "变", "快", "慢", "进", "退", "停", "动", "高", "低"]

SYMBOLS = ["□", "▉", "·", "￥", "☀", "☾", "○", "△", "▲", "◇",
           "◆", "☆", "↕", "↻", "◐", "◑", "●", "◈", "◉", "■"]

SYSTEM_PROMPT = (
    "你是一个AI符号系统专家。洛神系统使用一套内部符号来表示状态。"
    "现在需要为汉字分配一个最贴近其本义的符号。请从以下符号集中选择一个符号，"
    "并解释选择理由。符号集：['□', '▉', '·', '￥', '☀', '☾', '○', '△', '▲', "
    "'◇', '◆', '☆', '↕', '↻', '◐', '◑', '●', '◈', '◉', '■']。"
    "输出必须是JSON对象，字段包括：char（汉字）、symbol（选中的符号）、"
    "reason（选择理由，不超过20字）。不要添加任何额外文字。"
)


def query_llm(url, api_key, model, char):
    import living_engine
    _r = living_engine.generate_response(char, source="change_symbol_map",
                                         extra_context=SYSTEM_PROMPT)
    content = _r["reply"]
    if not content or content.startswith("[洛神"):
        raise ValueError("LLM call blocked or error")
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

        # 2.5 读取现有 hanzi_symbol_map.json
        try:
            with open('hanzi_symbol_map.json', 'r', encoding='utf-8') as f:
                smap = json.load(f)
            entries = smap.get("entries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            entries = {}
        if not entries:
            print(json.dumps({"error": "hanzi_symbol_map.json empty or not found"}))
            return

        # 2.4 调用大模型生成映射
        new_entries = {}
        for char in CHARS:
            try:
                result = query_llm(api_url, api_key, model, char)
                new_entries[char] = {
                    "symbol": result.get("symbol", ""),
                    "reason": result.get("reason", ""),
                }
            except Exception as e:
                print(json.dumps({"error": "request failed for " + char + ": " + str(e)}))

        # 2.6 合并进 entries
        for char, info in new_entries.items():
            entries[char] = info

        output = {
            "schema_version": 1,
            "module": "hanzi_symbol_map",
            "version": 1,
            "description": "汉字到洛神内部符号的映射，由大模型根据字源生成。",
            "entries": entries,
        }

        # 2.7 写回 hanzi_symbol_map.json
        with open('hanzi_symbol_map.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(output, ensure_ascii=False, indent=2) + '\n')

        # 2.8 计算 md5
        with open('hanzi_symbol_map.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.9 追加哈希链
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
            "file": "hanzi_symbol_map.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.10 标准输出
        with open('hanzi_symbol_map.json', 'r', encoding='utf-8') as f:
            print(f.read(), end="")
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
