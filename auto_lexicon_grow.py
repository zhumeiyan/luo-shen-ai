#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 自动骨字写入模块 auto_lexicon_grow.py"""
import hashlib
import json
import time


def append_chain(file_path, file_hash, prev_hash):
    timestamp = time.time()
    join_prev = prev_hash if prev_hash else ""
    record_hash = hashlib.md5(
        (file_hash + join_prev + str(timestamp)).encode('utf-8')
    ).hexdigest()
    record = {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": file_path,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return record


def md5_of(file_path):
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def last_prev_hash():
    with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1]).get("record_hash")


def main():
    try:
        # 2.1 读取状态匹配结果
        try:
            with open('state_match_log.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "state_match_log.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "state_match_log.jsonl empty or not found"}))
            return
        last_match = json.loads(lines[-1])
        state_words = last_match.get("state_words_match", [])
        change_words = last_match.get("change_words_match", [])

        # 2.2 读取汉字符号映射表
        try:
            with open('hanzi_symbol_map.json', 'r', encoding='utf-8') as f:
                symbol_map = json.load(f).get("entries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            symbol_map = {}
        if not symbol_map:
            print(json.dumps({"error": "hanzi_symbol_map.json empty or not found"}))
            return

        # 2.3 读取汉字知识库
        knowledge = {}
        try:
            with open('hanzi_knowledge_base.json', 'r', encoding='utf-8') as f:
                knowledge = json.load(f).get("entries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            knowledge = {}
        if not knowledge:
            knowledge = {}

        # 2.4 读取现有骨字库
        try:
            with open('core_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            lexicon = None
        entries = lexicon.get("entries", {}) if lexicon else {}
        if not entries:
            print(json.dumps({"error": "core_lexicon.json empty or not found"}))
            return

        # 2.5 构建候选字列表
        candidates = []
        for item in list(state_words) + list(change_words):
            if not item.get("matched"):
                continue
            word = item.get("word", "")
            if len(word) == 1:
                if word in symbol_map:
                    candidates.append(word)
            else:
                for ch in word:
                    if ch in symbol_map:
                        candidates.append(ch)
        candidate_chars = []
        for ch in candidates:
            if ch not in candidate_chars:
                candidate_chars.append(ch)

        # 2.6 自动写入骨字库
        added_chars = []
        skipped_chars = []
        for char in candidate_chars:
            symbol = symbol_map[char]["symbol"]
            kinfo = knowledge.get(char, {})
            ancient = kinfo.get("ancient", "") if isinstance(kinfo, dict) else ""
            modern = kinfo.get("modern", "") if isinstance(kinfo, dict) else ""
            meaning = (str(ancient) + " " + str(modern)).strip()
            if symbol in entries:
                skipped_chars.append(char)
                continue
            entries[symbol] = {"word": char, "meaning": meaning}
            added_chars.append(char)

        # 2.7 写回 core_lexicon.json
        with open('core_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(lexicon, ensure_ascii=False, indent=2) + '\n')

        # 2.8 生成自动写入日志
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "added_chars": added_chars,
            "skipped_chars": skipped_chars,
            "source": "auto_lexicon_grow",
        }

        # 2.9 追加写入 auto_lexicon_grow_log.jsonl
        with open('auto_lexicon_grow_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.10 计算 md5 并追加哈希链
        lexicon_hash = md5_of('core_lexicon.json')
        log_hash = md5_of('auto_lexicon_grow_log.jsonl')

        prev_hash = last_prev_hash()
        chain1 = append_chain('core_lexicon.json', lexicon_hash, prev_hash)
        chain2 = append_chain('auto_lexicon_grow_log.jsonl', log_hash, chain1["record_hash"])

        # 2.11 标准输出
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            print(f.read(), end="")
        print()
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain1, ensure_ascii=False))
        print(json.dumps(chain2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
