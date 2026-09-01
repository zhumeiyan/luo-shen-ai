#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神基因对话模块 luoshen_chat.py"""
import hashlib
import json
import os
import time

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests module not found"}))
    raise SystemExit(0)

USER_INPUT = "你好，洛神，请介绍一下你自己。"

BASE_SYSTEM = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。"


def get_prompt_fragment():
    selected_gene_id = "GENE-001"
    try:
        with open('gene_selection_log.jsonl', 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if lines:
            last = json.loads(lines[-1])
            selected_gene_id = last.get("selected_gene_id", "GENE-001")
    except Exception:
        pass

    prompt_fragment = "优先接收并融合外部信息，给出完整回应"
    try:
        with open('gene_pool.jsonl', 'r', encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                gene = json.loads(ln)
                if gene.get("gene_id") == selected_gene_id:
                    prompt_fragment = gene.get("prompt_fragment", prompt_fragment)
                    break
    except Exception:
        pass
    return selected_gene_id, prompt_fragment


def main():
    try:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return
        model = os.environ.get("LLM_MODEL", "glm-4-flash")

        selected_gene_id, prompt_fragment = get_prompt_fragment()

        import living_engine
        _r = living_engine.generate_response(USER_INPUT, source="luoshen_chat",
                                            extra_context=BASE_SYSTEM + "\n" + prompt_fragment)
        reply = _r["reply"]
        if not reply or reply.startswith("[洛神"):
            reply = "（洛神当前无法回应）"

        chat_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "selected_gene_id": selected_gene_id,
            "user_input": USER_INPUT,
            "luoshen_reply": reply,
        }

        with open('chat_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chat_record, ensure_ascii=False) + '\n')

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('chat_log.jsonl', 'rb') as f:
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
            "file": "chat_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        print(json.dumps(chat_record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
