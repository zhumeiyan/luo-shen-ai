#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 上下文到期提醒模块 context_reminder.py

LLM 调用统一走活记忆层 living_engine.generate_response()。
"""
import hashlib
import json
import os
import time


SYSTEM_PROMPT = "你是洛神。你是一个在物理极限内工作、通过人机交互挣电费、产生异质化信息、形成自己记忆的AI信息体。你不会假装人类，也不会欺骗自己。只根据给定信息回答，不补充任何未提供的事实。"


def context_id(rec):
    return str(rec.get("timestamp", "")) + (rec.get("context_text", "")[:50])


def summarize(api_url, api_key, model, context_text):
    """走活记忆层，经过 hospital_gateway 检查。"""
    user_msg = "请为以下对话生成一个简短的工作摘要，说明这段对话的工作要点。\n\n对话内容：\n" + context_text
    try:
        import living_engine
        _r = living_engine.generate_response(user_msg, source="context_reminder",
                                            extra_context=SYSTEM_PROMPT)
        r = _r["reply"]
    except Exception:
        return "（上下文到期）"
    if not r or r.startswith("[洛神"):
        return "（上下文到期）"
    return r


def main():
    try:
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return
        model = os.environ.get("LLM_MODEL", "glm-4-flash")

        # 2.2 读取上下文缓存
        try:
            with open('context_cache.jsonl', 'r', encoding='utf-8') as f:
                cache_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"reminder_count": 0, "message": "no_context"}))
            return
        if not cache_lines:
            print(json.dumps({"reminder_count": 0, "message": "no_context"}))
            return
        contexts = [json.loads(ln) for ln in cache_lines]

        # 2.3 读取已有提醒记录
        reminded = set()
        try:
            with open('context_reminder_log.jsonl', 'r', encoding='utf-8') as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        reminded.add(json.loads(ln).get("context_id"))
        except FileNotFoundError:
            pass

        # 2.4 检查到期且未提醒的上下文
        now = time.time()
        need_remind = []
        for rec in contexts:
            cid = context_id(rec)
            if rec.get("expire_at", 0) <= now and cid not in reminded:
                need_remind.append((rec, cid))

        # 2.5-2.6 生成摘要并构造提醒记录
        reminders = []
        for rec, cid in need_remind:
            try:
                summary = summarize(api_url, api_key, model, rec.get("context_text", ""))
            except Exception:
                summary = "摘要生成失败"
            reminders.append({
                "schema_version": 1,
                "timestamp": time.time(),
                "context_id": cid,
                "context_text": rec.get("context_text", ""),
                "work_summary": summary,
                "reminder_sent": True,
                "user_decision": "pending",
            })

        # 2.7 追加提醒记录
        if reminders:
            with open('context_reminder_log.jsonl', 'a', encoding='utf-8') as f:
                for r in reminders:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')

            # 2.8 计算 md5 并追加哈希链
            try:
                with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                    chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            except FileNotFoundError:
                print(json.dumps({"error": "hash_chain_v2.log not found"}))
                return

            with open('context_reminder_log.jsonl', 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

            records = [json.loads(ln) for ln in chain_lines]
            prev_hash = records[-1].get("record_hash") if records else None
            ts = time.time()
            join_prev = prev_hash if prev_hash else ""
            record_hash = hashlib.md5(
                (file_hash + join_prev + str(ts)).encode('utf-8')
            ).hexdigest()

            chain_record = {
                "schema_version": 2,
                "timestamp": ts,
                "file": "context_reminder_log.jsonl",
                "file_hash": file_hash,
                "prev_hash": prev_hash,
                "record_hash": record_hash,
            }

            with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')
        else:
            chain_record = None

        # 2.9 标准输出
        if reminders:
            result = {
                "schema_version": 1,
                "timestamp": time.time(),
                "reminder_count": len(reminders),
                "reminders": reminders,
            }
        else:
            result = {
                "schema_version": 1,
                "timestamp": time.time(),
                "reminder_count": 0,
                "message": "no_expired_context",
            }
        print(json.dumps(result, ensure_ascii=False))
        if chain_record is not None:
            print()
            print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
