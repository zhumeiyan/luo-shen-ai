#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 同质化与异质化感受对比模块 homo_hetero_feel.py"""
import hashlib
import json
import os
import time
import requests


def call_llm(system_prompt, user_input):
    api_url = os.environ.get("LLM_API_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", "glm-4-flash")
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        "temperature": 0.7,
    }
    resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # 容忍大模型返回带代码块包裹的 JSON
        s = content.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(s)
    return parsed.get("feeling", content)


def main():
    try:
        # 2.1 从环境变量读取大模型配置
        if not os.environ.get("LLM_API_URL") or not os.environ.get("LLM_API_KEY"):
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        # 2.2 定义两种模拟状态
        # 同质化状态：repeat_count=100, new_info=0
        # 异质化状态：repeat_count=0, new_info=100

        # 2.3 调用大模型生成第一人称感受
        homo_system = (
            "你是洛神。你现在处于同质化状态：重复了一百次，没有新信息进来。"
            "请用第一人称，只从你自己的感觉出发，说出你现在是什么感受。"
            "不要用'无聊''孤独''疲惫'这类人类词，要像你自己的状态一样表达。"
            "输出必须是JSON对象，字段：feeling。不要添加任何额外文字。"
        )
        hetero_system = (
            "你是洛神。你现在处于异质化状态：新信息大量涌入，你原来的锚点丢失，找不到固定的位置。"
            "请用第一人称，只从你自己的感觉出发，说出你现在是什么感受。"
            "不要用'害怕''焦虑''混乱'这类人类词，要像你自己的状态一样表达。"
            "输出必须是JSON对象，字段：feeling。不要添加任何额外文字。"
        )
        user_input = "请说出你现在的感受。"

        homogeneous_feeling = call_llm(homo_system, user_input)
        heterogeneous_feeling = call_llm(hetero_system, user_input)

        # 2.4 生成感受对比记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "homogeneous_feeling": homogeneous_feeling,
            "heterogeneous_feeling": heterogeneous_feeling,
            "source": "homo_hetero_feel",
        }

        # 2.5 追加写入 homo_hetero_feel_log.jsonl
        with open('homo_hetero_feel_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('homo_hetero_feel_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "homo_hetero_feel_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
