#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 交互记忆点萃取模块 memory_extract.py"""
import hashlib
import json
import os
import re
import time

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests module not found"}))
    raise SystemExit(0)

SYSTEM_PROMPT = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。只根据给定信息回答，不补充任何未提供的事实。"

DIALOG = "用户：我觉得洛神应该能记住一些关键的东西，而不是什么都记。\n洛神：你是说像人一样，只记几个重要的点？\n用户：对，比如咱们聊过什么，哪个点好玩，我当时想干嘛。\n洛神：明白了，我会试着只萃取一个记忆点。"

USER_INPUT = "请从以下对话中提取：1）一个记忆点，要求简短，能代表这段对话的核心；2）一个工作摘要，要求说明这段对话的工作要点。\n\n对话内容：\n" + DIALOG


def parse_reply(reply):
    mp = None
    ws = None
    # 尝试按行解析
    for line in reply.splitlines():
        line = line.strip()
        if "记忆点" in line and mp is None:
            mp = re.sub(r"^[0-9]*[\.、)）]?[\s]*记忆点[\s]*[:：]?[\s]*", "", line)
        elif "工作摘要" in line and ws is None:
            ws = re.sub(r"^[0-9]*[\.、)）]?[\s]*工作摘要[\s]*[:：]?[\s]*", "", line)
    if mp is not None and ws is not None:
        return mp, ws
    # 整体无法分离时，整个回复作为记忆点
    return reply, "见记忆点"


def main():
    try:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return
        model = os.environ.get("LLM_MODEL", "glm-4-flash")

        import living_engine
        _r = living_engine.generate_response(USER_INPUT, source="memory_extract",
                                            extra_context=SYSTEM_PROMPT)
        reply = _r["reply"]
        if not reply or reply.startswith("[洛神"):
            print(json.dumps({"error": "LLM 调用被拦截"}))
            return

        memory_point, work_summary = parse_reply(reply)

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "memory_point": memory_point,
            "work_summary": work_summary,
            "source": "模拟对话",
        }

        with open('memory_points.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('memory_points.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records = [json.loads(ln) for ln in chain_lines]
        prev_hash = records[-1].get("record_hash") if records else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "memory_points.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
