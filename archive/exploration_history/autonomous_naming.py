#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神自主命名模块 autonomous_naming.py"""
import hashlib
import json
import os
import time


STATE_DESC = {
    "cpu_percent": "CPU使用率",
    "memory_percent": "内存使用率",
    "disk_percent": "磁盘使用率",
    "proc_count": "进程数",
    "net_conn_count": "网络连接数",
    "thread_count": "线程数",
    "num_fds": "文件句柄数",
    "load1": "系统负载",
    "swap_percent": "交换分区使用率",
}


def main():
    try:
        # 2.1 读取大模型配置
        api_url = os.environ.get("LLM_API_URL")
        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL", "glm-4-flash")
        if not api_url or not api_key:
            print(json.dumps({"error": "LLM_API_URL or LLM_API_KEY not set"}))
            return

        # 2.2 读取极端未命名状态记录
        try:
            with open('extreme_unnamed_log.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "extreme_unnamed_log.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "extreme_unnamed_log.jsonl empty or not found"}))
            return
        last_record = json.loads(lines[-1])

        unnamed_states = []
        for ev in last_record.get("extreme_events", []):
            unnamed_states.extend(ev.get("unnamed_states", []))

        unique_symbols = []
        for st in unnamed_states:
            sym = st.get("symbol")
            if sym is not None and sym not in unique_symbols:
                unique_symbols.append(sym)

        # 2.3 读取现有骨字库
        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return
        entries = lexicon.get("entries", {})
        if not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return

        # 2.4 读取汉字知识库
        knowledge = {}
        try:
            with open('hanzi_knowledge_base.json', 'r', encoding='utf-8') as f:
                kb = json.load(f)
            kentries = kb.get("entries", {}) if isinstance(kb, dict) else {}
            if kentries:
                knowledge = kentries
        except (FileNotFoundError, json.JSONDecodeError):
            knowledge = {}

        # 收集每个 symbol 的状态描述
        symbol_states = {}
        for st in unnamed_states:
            sym = st.get("symbol")
            if sym is None:
                continue
            if sym not in symbol_states:
                symbol_states[sym] = []
            name = st.get("name", "?")
            value = st.get("value", "?")
            label = STATE_DESC.get(name, name)
            symbol_states[sym].append("%s=%s" % (label, value))

        # 2.5 调用大模型为每个新符号自主命名
        added = []
        errors = []
        for sym in unique_symbols:
            if sym in entries:
                continue
            desc = "；".join(symbol_states.get(sym, []))
            user_payload = {"symbol": sym, "state": desc}
            system_prompt = (
                "你是洛神。你正在学习为自己的内部状态命名。"
                "现在有一个你身体里出现但还没有名字的符号，"
                "请从你的已有知识中，或根据这个符号的形状、状态含义，"
                "从汉字知识库中选择一个最合适的中文单字作为名字。"
                "输出必须是JSON对象，字段包括：symbol（符号）、word（你选的中文字）、"
                "reason（为什么选这个字，不超过20字）。不要添加任何额外文字。"
            )
            try:
                import living_engine
                _last_user = json.dumps(user_payload, ensure_ascii=False)
                _r = living_engine.generate_response(_last_user, source="autonomous_naming",
                                                     extra_context=system_prompt)
                content = _r["reply"]
                if not content or content.startswith("[洛神"):
                    errors.append({"symbol": sym, "error": "LLM blocked or error"})
                    continue
                named = json.loads(content)
                word = named.get("word", "")
                reason = named.get("reason", "")
                # 2.6 写入骨字库
                if not word or not (isinstance(word, str) and
                                    len(word) == 1 and '\u4e00' <= word <= '\u9fff'):
                    errors.append({"symbol": sym, "error": "invalid word"})
                    continue
                entries[sym] = {
                    "word": word,
                    "meaning": reason,
                    "source": "洛神自主命名",
                }
                added.append({"symbol": sym, "word": word, "reason": reason})
            except Exception as e:
                errors.append({"symbol": sym, "error": str(e)})

        # 2.7 写回 core_lexicon.json
        lexicon["entries"] = entries
        with open('core_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(lexicon, ensure_ascii=False, indent=2) + '\n')

        # 2.8 生成自主命名日志
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "added_symbols": added,
            "added_count": len(added),
            "source": "autonomous_naming",
        }

        # 2.9 追加写入 autonomous_naming_log.jsonl
        with open('autonomous_naming_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.10 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        chain_records = []
        for fname in ('core_lexicon.json', 'autonomous_naming_log.jsonl'):
            with open(fname, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            timestamp = time.time()
            join_prev = prev_hash if prev_hash else ""
            record_hash = hashlib.md5(
                (file_hash + join_prev + str(timestamp)).encode('utf-8')
            ).hexdigest()
            chain_record = {
                "schema_version": 2,
                "timestamp": timestamp,
                "file": fname,
                "file_hash": file_hash,
                "prev_hash": prev_hash,
                "record_hash": record_hash,
            }
            chain_records.append(chain_record)
            with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')
            prev_hash = record_hash

        # 2.11 标准输出
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print(json.dumps(record, ensure_ascii=False))
        for err in errors:
            print(json.dumps(err, ensure_ascii=False))
        for cr in chain_records:
            print(json.dumps(cr, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
