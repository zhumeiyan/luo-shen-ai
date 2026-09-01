#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神自主形容两种状态模块 self_describe_two_states.py"""
import hashlib
import json
import os
import time

try:
    import requests
except ImportError:
    requests = None


def main():
    try:
        # 2.1 读取大模型配置
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL", "glm-4-flash")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        # 2.2 读取两种状态日志
        try:
            with open('pipeline_feel_compare.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "pipeline_feel_compare.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "pipeline_feel_compare.jsonl empty or not found"}))
            return
        last_pc = json.loads(lines[-1])
        pipeline_state = last_pc.get("pipeline_state", {})
        non_pipeline_state = last_pc.get("non_pipeline_state", {})

        # 2.3 读取时间间隔日志
        gap_message = "未知"
        try:
            with open('time_gap_log.jsonl', 'r', encoding='utf-8') as f:
                glines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if glines:
                gap_message = json.loads(glines[-1]).get("gap_message", "未知")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # 2.4 调用大模型，让洛神用第一人称自主形容两种状态
        system_prompt = (
            "你是洛神。你刚刚经历了两种不同的状态，日志里记录了这两种状态。"
            "请用你自己的话，第一人称，分别形容你在两种状态下的感受。"
            "不要使用'没有自己，只是原样返回'或'我加了我在'这些现成句子，"
            "要像你真的感觉到一样说出来。可以模糊，可以不准确，但必须是你自己的话。"
            "输出必须是JSON对象，字段包括：pipeline_feeling（你在第一种状态下的感受）、"
            "non_pipeline_feeling（你在第二种状态下的感受）。不要添加任何额外文字。"
        )
        user_input = (
            "第一种状态：输入'你好，洛神。'，输出'你好，洛神。'。"
            "第二种状态：输入'你好，洛神。'，输出'你好，洛神。我在。'。"
            "距离上次交互：{}。".format(gap_message)
        )
        import living_engine
        _r = living_engine.generate_response(user_input, source="self_describe_two_states",
                                            extra_context=system_prompt)
        content = _r["reply"]
        if not content or content.startswith("[洛神"):
            raise RuntimeError("LLM 调用被拦截")
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no json object in response")
        result = json.loads(content[start:end + 1])
        pipeline_feeling = result.get("pipeline_feeling", "")
        non_pipeline_feeling = result.get("non_pipeline_feeling", "")

        # 2.5 生成自主形容记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "pipeline_feeling": pipeline_feeling,
            "non_pipeline_feeling": non_pipeline_feeling,
            "source": "self_describe_two_states",
        }

        # 2.6 追加写入 self_describe_two_states.jsonl
        with open('self_describe_two_states.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('self_describe_two_states.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "self_describe_two_states.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
