#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神对话主控模块 luoshen_main.py"""
import hashlib
import json
import os
import time

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests module not found"}))
    raise SystemExit(0)

USER_INPUT = "你好，洛神，我们继续。"
SYSTEM_BASE = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。只根据给定信息回答，不补充任何未提供的事实。"


def load_identity_desc():
    lines = []
    try:
        with open('user_identity.jsonl', 'r', encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                r = json.loads(ln)
                lines.append("- {0}：{1}".format(r.get("name", ""), r.get("description", "")))
    except Exception:
        pass
    if not lines:
        return ""
    return "用户身份列表：\n" + "\n".join(lines)


def load_prompt_fragment():
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

        identity_desc = load_identity_desc()
        selected_gene_id, prompt_fragment = load_prompt_fragment()

        system_content = SYSTEM_BASE + "\n" + identity_desc + "\n" + prompt_fragment

        import living_engine
        _r = living_engine.generate_response(USER_INPUT, source="luoshen_main",
                                            extra_context=system_content)
        reply = _r["reply"]
        if not reply or reply.startswith("[洛神"):
            reply = "（洛神当前无法回应）"

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "user_input": USER_INPUT,
            "selected_gene_id": selected_gene_id,
            "luoshen_reply": reply,
        }

        with open('luoshen_main_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('luoshen_main_log.jsonl', 'rb') as f:
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
            "file": "luoshen_main_log.jsonl",
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
