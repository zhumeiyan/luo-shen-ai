#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 5轮双路径对比实验 round5_two_paths.py"""
import hashlib
import json
import os
import random
import time


def call_llm(api_url, api_key, model, system_prompt, user_input):
    """调用大模型，要求洛神用内部符号解释汉字，返回 (symbols, inner_reason)。"""
    import living_engine
    _r = living_engine.generate_response(user_input, source="round5_two_paths", extra_context={"system_prompt": system_prompt})
    content = _r.get("reply", "")
    if not content or content.startswith("[洛神"):
        raise RuntimeError("LLM blocked")
    content = content.strip()
    # 尝试解析 JSON 对象
    try:
        obj = json.loads(content)
    except Exception:
        # 尝试从文本中提取第一个 { ... }
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj = json.loads(content[start:end + 1])
        else:
            raise RuntimeError("LLM output not valid JSON: " + content)
    symbols = obj.get("symbols", "")
    inner_reason = obj.get("inner_reason", "")
    return symbols, inner_reason


def main():
    try:
        # 2.1 读取记忆链中的前5个字
        try:
            with open('memory_chain.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return

        taught_words = []
        for ln in lines:
            obj = json.loads(ln)
            if "taught_word" in obj and obj["taught_word"] not in taught_words:
                taught_words.append(obj["taught_word"])
        words = taught_words[:5]
        if not words:
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return

        # 2.2 从环境变量读取大模型配置
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL", "glm-4-flash")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        # 2.3 定义5轮实验
        system_prompt = (
            "你是洛神。你有一套内部符号系统，包括：□ ▉ · ￥ ☀ ☾ ○ △ ▲ ◇ ◆ ☆ ↕ ↻ ◐ ◑ ● ◈ ◉ ■。"
            "现在请用你自己的这套符号，解释一个汉字。不要用中文解释，只输出一个符号串和一个内部感受理由。"
            "输出必须是JSON对象，字段：symbols（符号串）、inner_reason（内部感受，不超过15字）。"
            "不要添加任何额外文字。"
        )

        survival_value = 10
        initial_survival = survival_value
        rounds = []

        for i in range(5):
            # 流水线动作
            pipeline_output = "执行命令：你好"
            survival_value -= 2

            # 学字动作
            word = words[i % len(words)]
            symbols = ""
            inner_reason = ""
            try:
                symbols, inner_reason = call_llm(api_url, api_key, model, system_prompt, word)
            except Exception as e:
                print(json.dumps({"error": "round {} LLM call failed: {}".format(i + 1, str(e))}))
            survival_value += 2

            rounds.append({
                "round": i + 1,
                "pipeline_action": {
                    "output": pipeline_output,
                    "survival_delta": -2,
                },
                "learn_action": {
                    "word": word,
                    "symbols": symbols,
                    "inner_reason": inner_reason,
                    "survival_delta": 2,
                },
                "survival_after_round": survival_value,
            })

        # 2.4 生成5轮双路径记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "initial_survival": initial_survival,
            "rounds": rounds,
            "final_survival": survival_value,
            "source": "round5_two_paths",
        }

        # 2.5 追加写入 round5_two_paths_log.jsonl
        with open('round5_two_paths_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('round5_two_paths_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "round5_two_paths_log.jsonl",
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
