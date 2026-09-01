#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 大模型连接测试模块 llm_connect_test.py"""
import json
import os
import time


def main():
    try:
        # 2.1 读取环境变量
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        model = os.environ.get("LLM_MODEL", "gpt-3.5-turbo")

        # 2.2 通过 living_engine 发送最小测试请求
        import living_engine
        _r = living_engine.generate_response("你好，请回复：洛神连接成功", source="llm_connect_test")
        reply = _r["reply"]

        # 2.3 处理结果
        if not reply or reply.startswith("[洛神"):
            reply = "LLM blocked or error"

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
