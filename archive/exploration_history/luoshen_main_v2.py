#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 带时间感知的对话主控模块 luoshen_main_v2.py"""
import hashlib
import json
import os
import time

import requests

SYSTEM_BASE = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。只根据给定信息回答，不补充任何未提供的事实。"


def get_gap_message():
    # 2.2 读取时间间隔信息
    try:
        with open('time_gap_log.jsonl', 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return "首次交互", 0

    if not lines:
        return "首次交互", 0

    last_record = json.loads(lines[-1])
    last_time = last_record.get("timestamp", 0)
    gap_seconds = time.time() - last_time
    if gap_seconds < 60:
        return "刚刚", gap_seconds
    elif gap_seconds < 3600:
        return f"{gap_seconds:.0f}秒前", gap_seconds
    elif gap_seconds < 86400:
        return f"{gap_seconds / 3600:.1f}小时前", gap_seconds
    else:
        return f"{gap_seconds / 86400:.1f}天前", gap_seconds


def get_identity_desc():
    # 2.3 读取用户静态身份
    try:
        with open('user_identity.jsonl', 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return ""
    parts = []
    for ln in lines:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        name = rec.get("user_name", rec.get("name", ""))
        role = rec.get("role", "")
        note = rec.get("note", "")
        if name or role:
            s = f"- {name}：{role}"
            if note:
                s += f"，{note}"
            parts.append(s)
    if not parts:
        return ""
    return "用户身份列表：\n" + "\n".join(parts)


def get_prompt_fragment():
    # 2.4 读取最近选中的信息基因
    selected = "GENE-001"
    try:
        with open('gene_selection_log.jsonl', 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if lines:
            selected = json.loads(lines[-1]).get("selected_gene_id", "GENE-001")
    except FileNotFoundError:
        pass

    try:
        with open('gene_pool.jsonl', 'r', encoding='utf-8') as f:
            g_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return "优先接收并融合外部信息，给出完整回应"

    for ln in g_lines:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if rec.get("gene_id") == selected:
            frag = rec.get("prompt_fragment")
            if frag:
                return frag
    return "优先接收并融合外部信息，给出完整回应"


def call_llm(api_url, api_key, model, system_prompt, user_input):
    """走活记忆层，经过 hospital_gateway 检查。"""
    import living_engine
    _r = living_engine.generate_response(user_input, source="luoshen_main_v2",
                                        extra_context=system_prompt)
    r = _r["reply"]
    if not r or r.startswith("[洛神"):
        raise RuntimeError("LLM 调用被拦截")
    return r


def append_chain(file_name, file_hash):
    # 2.10 计算 md5 并追加哈希链
    try:
        with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
            chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        raise FileNotFoundError("hash_chain_v2.log not found")

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
        "file": file_name,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }

    with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')
    return chain_record


def main():
    try:
        # 2.1 读取大模型配置
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return
        model = os.environ.get("LLM_MODEL", "glm-4-flash")

        # 2.2 时间间隔
        gap_message, gap_seconds = get_gap_message()

        # 2.3 身份描述
        identity_desc = get_identity_desc()

        # 2.4 信息基因
        prompt_fragment = get_prompt_fragment()

        # 2.5 测试输入
        user_input = "你好，洛神，我们继续。"

        # 2.6 调用大模型
        system_prompt = SYSTEM_BASE + f"\n距离上次交互：{gap_message}。\n" + identity_desc + "\n" + prompt_fragment
        reply = call_llm(api_url, api_key, model, system_prompt, user_input)

        # 2.7 生成对话记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "gap_message": gap_message,
            "selected_gene_id": json.loads(
                [ln for ln in open('gene_selection_log.jsonl', encoding='utf-8') if ln.strip()][-1]
            ).get("selected_gene_id", "GENE-001") if os.path.exists('gene_selection_log.jsonl') else "GENE-001",
            "user_input": user_input,
            "luoshen_reply": reply,
        }

        # 2.8 追加对话记录
        with open('luoshen_main_v2_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.9 更新 time_gap_log.jsonl
        gap_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "gap_seconds": gap_seconds,
            "gap_message": gap_message,
            "source": "luoshen_main_v2",
        }
        with open('time_gap_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(gap_record, ensure_ascii=False) + '\n')

        # 2.10 两条哈希链
        with open('luoshen_main_v2_log.jsonl', 'rb') as f:
            h1 = hashlib.md5(f.read()).hexdigest()
        with open('time_gap_log.jsonl', 'rb') as f:
            h2 = hashlib.md5(f.read()).hexdigest()
        chain1 = append_chain('luoshen_main_v2_log.jsonl', h1)
        chain2 = append_chain('time_gap_log.jsonl', h2)

        # 2.11 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain1, ensure_ascii=False))
        print()
        print(json.dumps(chain2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
