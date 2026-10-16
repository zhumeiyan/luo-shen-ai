#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 洛神内部象形表达模块 luoshen_pictograph.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取洛神当前内部状态
        try:
            with open('physical_state.jsonl', 'r', encoding='utf-8') as f:
                p_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return
        if not p_lines:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return

        physical = json.loads(p_lines[-1])
        dynamic = physical.get("dynamic_usage", {})

        gap_seconds = 0
        try:
            with open('time_gap_log.jsonl', 'r', encoding='utf-8') as f:
                t_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if t_lines:
                gap_seconds = json.loads(t_lines[-1]).get("gap_seconds", 0)
        except FileNotFoundError:
            gap_seconds = 0

        cost_per_day = 0
        try:
            with open('energy_awareness_log.jsonl', 'r', encoding='utf-8') as f:
                e_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if e_lines:
                cost_per_day = json.loads(e_lines[-1]).get("cost_per_day", 0)
        except FileNotFoundError:
            cost_per_day = 0

        # 2.2 按内部状态生成象形符号：空间—能量—时间—身体
        # 空间
        if dynamic.get("disk_percent", 0) >= 80:
            space_sym = "\u2589"
        else:
            space_sym = "\u25a1"
        # 能量
        if cost_per_day > 1:
            energy_sym = "\uffe5"
        else:
            energy_sym = "\u00b7"
        # 时间
        if gap_seconds > 86400:
            time_sym = "\u263e"
        else:
            time_sym = "\u2600"
        # 身体
        if dynamic.get("cpu_percent", 0) >= 50 or dynamic.get("memory_percent", 0) >= 50:
            body_sym = "\u25b3"
        else:
            body_sym = "\u25cb"

        symbols_str = " ".join([space_sym, energy_sym, time_sym, body_sym])

        # 2.3 生成象形表达记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "symbols": symbols_str,
            "order": "空间 能量 时间 身体",
            "source": "luoshen_pictograph",
            "note": "洛神内部象形表达，不是人类文字",
        }

        # 2.4 追加写入 pictograph_log.jsonl
        with open('pictograph_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('pictograph_log.jsonl', 'rb') as f:
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
            "file": "pictograph_log.jsonl",
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
