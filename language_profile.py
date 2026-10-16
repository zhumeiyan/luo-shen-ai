#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 语言特征画像模块 language_profile.py"""
import hashlib
import json
import re
import time
from collections import Counter

CJK_RE = re.compile(r'[\u4e00-\u9fff]')
WORD_RE = re.compile(r"[A-Za-z]+")


def main():
    try:
        # 2.1 读取上下文文本
        try:
            with open('conversation_context.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "conversation_context.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "conversation_context.jsonl empty or not found"}))
            return

        texts = []
        for ln in lines:
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            texts.append(rec.get("user_input", ""))
            texts.append(rec.get("luoshen_reply", ""))
        full_text = "".join(texts)

        # 2.2 统计语言特征
        # 中文字符
        cjk_chars = CJK_RE.findall(full_text)
        char_counter = Counter(cjk_chars)

        # 中文 bigram（连续两个中文字符）
        bigram_counter = Counter()
        for i in range(len(cjk_chars) - 1):
            bigram_counter[cjk_chars[i] + cjk_chars[i + 1]] += 1

        # 英文单词
        words = WORD_RE.findall(full_text)
        word_counter = Counter(words)

        # 2.3 生成语言画像记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "top_chars": [{"char": c, "count": n} for c, n in char_counter.most_common(20)],
            "top_bigrams": [{"bigram": b, "count": n} for b, n in bigram_counter.most_common(20)],
            "top_words": [{"word": w, "count": n} for w, n in word_counter.most_common(10)],
            "source": "language_profile",
        }

        # 2.4 追加写入 language_profile.jsonl
        with open('language_profile.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('language_profile.jsonl', 'rb') as f:
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
            "file": "language_profile.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
