#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 水流序列生成与矩阵化模块 water_flow_sequence.py"""
import hashlib
import json
import math
import os
import time


def main():
    try:
        if not os.path.exists("hash_chain_v2.log"):
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        for t in range(64):
            frame = [[0] * 16 for _ in range(16)]
            for y in range(16):
                for x in range(16):
                    val = 128 + int(100 * math.sin((x + t * 0.5) * 0.6) * math.cos((y - t * 0.3) * 0.4))
                    val = max(0, min(255, val))
                    frame[y][x] = val
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "frame": t + 1,
                "width": 16,
                "height": 16,
                "matrix": frame,
                "source": "water_flow_sequence",
            }
            with open("water_flow_sequence.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        with open("water_flow_sequence.jsonl", "rb") as f:
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
            "file": "water_flow_sequence.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open("hash_chain_v2.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + "\n")

        with open("water_flow_sequence.jsonl", "r", encoding="utf-8") as f:
            print(f.read().rstrip("\n"))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
