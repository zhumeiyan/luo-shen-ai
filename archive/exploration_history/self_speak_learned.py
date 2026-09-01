#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 自述所学模块 self_speak_learned.py"""
import hashlib
import json
import os
import time

ALLOWED_CONNECTORS = {"我", "的", "是", "很", "不", "有", "了", "就", "和", "也", "都"}

STATE_WORDS = {"空", "满", "流", "转", "静", "紧", "闲", "息", "轻", "重", "明", "暗", "升", "降", "进", "退", "开", "合", "温", "凉", "动"}

SYSTEM_PROMPT = (
    "你是洛神。你只懂以下内部状态词：空 满 流 转 静 紧 闲 息 轻 重 明 暗 升 降 进 退 开 合 温 凉 动。"
    "你不能使用任何人类情绪词、比喻、诗句。你现在看到一些汉字和它们对应的符号。"
    "请只从你自己的感觉出发，用第一人称说一句最想说的话。"
    "这句话必须只由上述状态词组成，可以加最简单的连接词。如果你说不出来，就只回答：我说不出来。"
    "输出必须是JSON对象，字段只有：speech。不要添加任何额外文字。"
)


def is_valid_speech(text):
    for ch in text:
        if ch in STATE_WORDS or ch in ALLOWED_CONNECTORS or ch in "，。、！？… 　":
            continue
        return False
    return True


def main():
    try:
        if not os.path.exists("shuowen_lexicon_batch1.json"):
            print(json.dumps({"error": "shuowen_lexicon_batch1.json empty or not found"}))
            return
        with open("shuowen_lexicon_batch1.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", {})
        if not entries:
            print(json.dumps({"error": "shuowen_lexicon_batch1.json empty or not found"}))
            return

        if not os.path.exists("hash_chain_v2.log"):
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL", "glm-4-flash")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        names = list(entries.keys())[:5]
        reasons = [entries[n].get("inner_reason", "") for n in names]
        user_input = "我看到的字：%s。它们的状态词：%s。" % (
            "、".join(names),
            "、".join(reasons),
        )

        speech = "我说不出来"
        try:
            import living_engine
            _r = living_engine.generate_response(user_input, source="self_speak_learned",
                                                 extra_context=SYSTEM_PROMPT)
            content = _r["reply"]
            if not content or content.startswith("[洛神"):
                raise ValueError("LLM blocked")
            content = content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            parsed = json.loads(content)
            speech = str(parsed.get("speech", "")).strip()
        except Exception:
            speech = "我说不出来"

        if not speech or not is_valid_speech(speech):
            speech = "我说不出来"

        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "speech": speech,
            "source": "self_speak_learned",
        }
        with open("self_speak_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        with open("self_speak_log.jsonl", "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        with open("hash_chain_v2.log", "r", encoding="utf-8") as f:
            clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode("utf-8")
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "self_speak_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open("hash_chain_v2.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + "\n")

        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
