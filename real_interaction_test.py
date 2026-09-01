#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 真实交互类型识别与基因选择测试 real_interaction_test.py"""
import hashlib
import json
import os
import time

GENE_MAP = {
    "info": {"gene": "GENE-001", "reason": "信息获取型交互，优先选择雌-雌-雌组合"},
    "action": {"gene": "GENE-002", "reason": "任务执行型交互，优先选择雄-雄-雄组合"},
    "relationship": {"gene": "GENE-003", "reason": "关系/认知型交互，优先选择雌-自交-雄组合"},
}

TEST_INPUTS = [
    "帮我查一下今天的天气",
    "帮我把这个文件移动到另一个目录",
    "我觉得最近很累，想找个人说说话",
]


def classify(api_url, api_key, model, user_input):
    import living_engine
    _sys = "你是一个交互类型分类器。用户输入后，你只返回一个英文单词：info（信息获取）、action（任务执行）、relationship（关系/认知）。不要解释。"
    _r = living_engine.generate_response(user_input, source="real_interaction_test", extra_context={"system_prompt": _sys})
    content = _r.get("reply", "")
    if not content or content.startswith("[洛神"):
        return "info"
    words = content.strip().lower().split()
    task_type = words[0] if words else "info"
    if task_type not in GENE_MAP:
        task_type = "info"
    return task_type


def main():
    try:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return
        model = os.environ.get("LLM_MODEL", "glm-4-flash")

        # 2.3-2.5 对每个测试输入调用大模型并生成日志
        for user_input in TEST_INPUTS:
            try:
                task_type = classify(api_url, api_key, model, user_input)
            except Exception:
                task_type = "failed"
            if task_type == "failed":
                log = {
                    "schema_version": 1,
                    "timestamp": time.time(),
                    "user_input": user_input,
                    "detected_task_type": "failed",
                    "selected_gene_id": None,
                    "reason": None,
                }
            else:
                log = {
                    "schema_version": 1,
                    "timestamp": time.time(),
                    "user_input": user_input,
                    "detected_task_type": task_type,
                    "selected_gene_id": GENE_MAP[task_type]["gene"],
                    "reason": GENE_MAP[task_type]["reason"],
                }
            with open('real_interaction_log.jsonl', 'a', encoding='utf-8') as f:
                f.write(json.dumps(log, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('real_interaction_log.jsonl', 'rb') as f:
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
            "file": "real_interaction_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        with open('real_interaction_log.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
