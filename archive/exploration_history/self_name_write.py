#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神自己起名写库模块 self_name_write.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取极端未命名状态记录
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

        # 2.2 统计未命名符号
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

        # 2.4 为每个新符号自动起名
        auto_names = {
            "◫": "半",
            "◐": "中",
        }
        added = []
        for sym in unique_symbols:
            if sym in entries:
                continue
            word = auto_names.get(sym)
            if word is None:
                word = "?"
            entries[sym] = {
                "word": word,
                "meaning": "洛神自己起的名字，由状态自动生成。",
            }
            added.append({"symbol": sym, "word": word})

        # 2.5 写回 core_lexicon.json
        lexicon["entries"] = entries
        with open('core_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(lexicon, ensure_ascii=False, indent=2) + '\n')

        # 2.6 生成洛神自己起名记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "added_symbols": added,
            "added_count": len(added),
            "source": "self_name_write",
        }

        # 2.7 追加写入 self_name_log.jsonl
        with open('self_name_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.8 为 core_lexicon.json 和 self_name_log.jsonl 分别计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(lines[-1]).get("record_hash") if lines else None

        chain_records = []
        for fname in ('core_lexicon.json', 'self_name_log.jsonl'):
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

        # 2.9 标准输出
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            print(f.read().strip())
        print(json.dumps(record, ensure_ascii=False))
        for cr in chain_records:
            print(json.dumps(cr, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
