#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 用户静态身份模块 user_identity_init.py"""
import hashlib
import json
import os
import time

USER_INPUT = "你认识朱美岩吗？她是谁？"
SYSTEM_BASE = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。"


def load_user_records():
    records = []
    with open('user_identity.jsonl', 'r', encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                records.append(json.loads(ln))
    return records


def build_identity_desc(records):
    lines = []
    for r in records:
        lines.append("- {0}：{1}".format(r.get("name", ""), r.get("description", "")))
    return "用户身份列表：\n" + "\n".join(lines)


def append_chain(file_path, file_hash, timestamp):
    with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
        chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    records = [json.loads(ln) for ln in chain_lines]
    prev_hash = records[-1].get("record_hash") if records else None
    join_prev = prev_hash if prev_hash else ""
    record_hash = hashlib.md5(
        (file_hash + join_prev + str(timestamp)).encode('utf-8')
    ).hexdigest()
    chain_record = {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')
    return chain_record


def main():
    try:
        # 2.1 创建用户静态身份文件
        user_record = {
            "schema_version": 1,
            "user_id": "ZMY-001",
            "name": "朱美岩",
            "role": "designer",
            "permissions": ["read_all", "write_audit", "modify_rules", "final_interpretation"],
            "description": "洛神系统设计者本人，拥有最终解释权",
        }
        with open('user_identity.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(user_record, ensure_ascii=False) + '\n')

        # 2.2 读取大模型配置
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return
        model = os.environ.get("LLM_MODEL", "glm-4-flash")

        # 2.3 读取用户身份信息并构造描述
        records = load_user_records()
        identity_desc = build_identity_desc(records)

        # 2.4 调用大模型测试识别
        import living_engine
        _sys = SYSTEM_BASE + "\n" + identity_desc
        _r = living_engine.generate_response(USER_INPUT, source="user_identity_init",
                                             extra_context=_sys)
        reply = _r["reply"]
        if not reply or reply.startswith("[洛神"):
            print(json.dumps({"error": "LLM 调用被拦截"}))
            return

        # 2.5-2.6 生成并追加测试日志
        log_record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "question": USER_INPUT,
            "luoshen_reply": reply,
        }
        with open('user_identity_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_record, ensure_ascii=False) + '\n')

        # 2.7 为两个文件分别追加哈希链
        ts1 = time.time()
        with open('user_identity.jsonl', 'rb') as f:
            hash1 = hashlib.md5(f.read()).hexdigest()
        chain1 = append_chain('user_identity.jsonl', hash1, ts1)

        ts2 = time.time()
        with open('user_identity_log.jsonl', 'rb') as f:
            hash2 = hashlib.md5(f.read()).hexdigest()
        chain2 = append_chain('user_identity_log.jsonl', hash2, ts2)

        # 2.8 标准输出
        with open('user_identity.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print()
        with open('user_identity_log.jsonl', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print()
        print(json.dumps(chain1, ensure_ascii=False))
        print()
        print(json.dumps(chain2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
