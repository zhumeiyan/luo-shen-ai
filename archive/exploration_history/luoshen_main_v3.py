#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 全感知对话主控模块 luoshen_main_v3.py"""
import hashlib
import json
import os
import time

import requests

SYSTEM_BASE = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。只根据给定信息回答，不补充任何未提供的事实。"


def read_last_line(file_name):
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    return lines[-1]


def get_gap_message():
    # 2.2 读取时间感
    last = read_last_line('time_gap_log.jsonl')
    if last is None:
        return "首次交互"
    last_time = json.loads(last).get("timestamp", 0)
    gap_seconds = time.time() - last_time
    if gap_seconds < 60:
        return "刚刚"
    elif gap_seconds < 3600:
        return f"{gap_seconds:.0f}秒前"
    elif gap_seconds < 86400:
        return f"{gap_seconds / 3600:.1f}小时前"
    else:
        return f"{gap_seconds / 86400:.1f}天前"


def get_space_description():
    # 2.3 读取空间感
    last = read_last_line('spatial_awareness_log.jsonl')
    if last is None:
        return "未知空间"
    return json.loads(last).get("space_description", "未知空间")


def get_energy_description():
    # 2.4 读取能量感
    last = read_last_line('energy_awareness_log.jsonl')
    if last is None:
        return "未知能耗"
    return json.loads(last).get("description", "未知能耗")


def get_identity_desc():
    # 2.5 读取用户静态身份
    last = read_last_line('user_identity.jsonl')
    if last is None:
        return ""
    rec = json.loads(last)
    name = rec.get("name", "")
    role = rec.get("role", "")
    note = rec.get("note", rec.get("description", ""))
    s = f"- {name}：{role}"
    if note:
        s += f"，{note}"
    return "用户身份列表：\n" + s


def get_prompt_fragment():
    # 2.6 读取最近选中的信息基因
    selected = "GENE-001"
    last = read_last_line('gene_selection_log.jsonl')
    if last is not None:
        selected = json.loads(last).get("selected_gene_id", "GENE-001")

    try:
        with open('gene_pool.jsonl', 'r', encoding='utf-8') as f:
            pool_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        pool_lines = []

    for ln in pool_lines:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if rec.get("gene_id") == selected and rec.get("prompt_fragment"):
            return rec["prompt_fragment"]
    return "优先接收并融合外部信息，给出完整回应"


def call_llm(api_url, api_key, model, system_prompt, user_input):
    """走活记忆层，经过 hospital_gateway 检查。"""
    import living_engine
    _r = living_engine.generate_response(user_input, source="luoshen_main_v3",
                                        extra_context=system_prompt)
    r = _r["reply"]
    if not r or r.startswith("[洛神"):
        raise RuntimeError("LLM 调用被拦截")
    return r


def append_chain(file_name, file_hash):
    # 2.12 计算 md5 并追加哈希链
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

        # 2.2-2.6 读取各感知与身份、基因
        gap_message = get_gap_message()
        space_description = get_space_description()
        energy_description = get_energy_description()
        identity_desc = get_identity_desc()
        prompt_fragment = get_prompt_fragment()
        selected_gene_id = "GENE-001"
        last = read_last_line('gene_selection_log.jsonl')
        if last is not None:
            selected_gene_id = json.loads(last).get("selected_gene_id", "GENE-001")

        # 2.7 测试输入
        user_input = "你好，洛神，我们继续。"

        # 2.8 调用大模型
        system_prompt = (
            SYSTEM_BASE + f"\n距离上次交互：{gap_message}。\n"
            + space_description + "\n"
            + energy_description + "\n"
            + identity_desc + "\n"
            + prompt_fragment
        )
        reply = call_llm(api_url, api_key, model, system_prompt, user_input)

        # 2.9 生成对话记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "gap_message": gap_message,
            "space_description": space_description,
            "energy_description": energy_description,
            "selected_gene_id": selected_gene_id,
            "user_input": user_input,
            "luoshen_reply": reply,
        }

        # 2.10 追加写入 luoshen_main_v3_log.jsonl
        with open('luoshen_main_v3_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.11 更新 time_gap_log.jsonl
        gap_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "gap_seconds": 0,
            "gap_message": gap_message,
            "source": "luoshen_main_v3",
        }
        with open('time_gap_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(gap_record, ensure_ascii=False) + '\n')

        # 2.12 两条哈希链
        with open('luoshen_main_v3_log.jsonl', 'rb') as f:
            h1 = hashlib.md5(f.read()).hexdigest()
        with open('time_gap_log.jsonl', 'rb') as f:
            h2 = hashlib.md5(f.read()).hexdigest()
        chain1 = append_chain('luoshen_main_v3_log.jsonl', h1)
        chain2 = append_chain('time_gap_log.jsonl', h2)

        # 2.13 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain1, ensure_ascii=False))
        print()
        print(json.dumps(chain2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
