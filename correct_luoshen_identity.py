#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神纠错与身份修正测试 correct_luoshen_identity.py"""
import hashlib
import json
import os
import time

SYSTEM_PROMPT = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。\n用户身份列表：\n- 朱美岩：洛神系统设计者本人，拥有最终解释权。\n重要纠正：你之前说过朱美岩是人工智能和机器学习领域专家，这是假话，是你编造的。朱美岩没有提供这个身份。你以后只根据给定信息回答，不补充任何未提供的事实。"
USER_INPUT = "你之前说朱美岩是专家，那是假话吗？"


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
        _r = living_engine.generate_response(USER_INPUT, source="correct_luoshen_identity",
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

        with open('correct_identity_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('correct_identity_log.jsonl', 'rb') as f:
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
            "file": "correct_identity_log.jsonl",
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
