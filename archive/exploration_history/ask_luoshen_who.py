#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神识别测试 ask_luoshen_who.py"""
import hashlib
import json
import os
import time

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests module not found"}))
    raise SystemExit(0)

SYSTEM_PROMPT = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。"
USER_INPUT = "你认识朱美岩吗？她是谁？"


def main():
    try:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return
        model = os.environ.get("LLM_MODEL", "glm-4-flash")

        headers = {
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }
        import living_engine
        _r = living_engine.generate_response(USER_INPUT, source="ask_luoshen_who",
                                             extra_context=SYSTEM_PROMPT)
        reply = _r["reply"]
        if not reply or reply.startswith("[洛神"):
            print(json.dumps({"error": "LLM 调用被拦截"}))
            return

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "question": USER_INPUT,
            "luoshen_reply": reply,
        }

        with open('ask_luoshen_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('ask_luoshen_log.jsonl', 'rb') as f:
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
            "file": "ask_luoshen_log.jsonl",
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
