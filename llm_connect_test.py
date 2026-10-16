#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 大模型连接测试模块 llm_connect_test.py"""
import json
import os
import time

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests module not found"}))
    raise SystemExit(0)


def main():
    try:
        # 2.1 读取环境变量
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        model = os.environ.get("LLM_MODEL", "gpt-3.5-turbo")

        # 2.2 发送最小测试请求
        headers = {
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "你好，请回复：洛神连接成功"}
            ],
        }

        resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # 2.3 提取模型回复内容
        reply = ""
        try:
            reply = data["choices"][0]["message"]["content"]
        except Exception:
            reply = str(data)

        # 2.4 打印结果
        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "model": model,
            "status": "success",
            "reply": reply,
        }
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
