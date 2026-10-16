#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 汉字字节矩阵传入模块 char_matrix.py"""
import hashlib
import json
import os
import time


def main():
    try:
        if not os.path.exists("memory_chain.jsonl"):
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return
        words = []
        with open("memory_chain.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                w = item.get("taught_word", "")
                if w:
                    words.append(w)
        if not words:
            print(json.dumps({"error": "memory_chain.jsonl empty or not found"}))
            return

        if not os.path.exists("hash_chain_v2.log"):
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        for ch in words:
            raw = ch.encode("utf-8")
            hex_list = ["%02x" % b for b in raw]
            matrix = list(raw)
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "char": ch,
                "bytes": hex_list,
                "matrix": matrix,
                "source": "char_matrix",
            }
            with open("char_matrix.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        with open("char_matrix.jsonl", "rb") as f:
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
            "file": "char_matrix.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open("hash_chain_v2.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + "\n")

        with open("char_matrix.jsonl", "r", encoding="utf-8") as f:
            print(f.read().rstrip("\n"))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
