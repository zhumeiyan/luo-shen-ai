#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 空间感知模块 spatial_awareness.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取 physical_state.jsonl 最后一条
        try:
            with open('physical_state.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "physical_state.jsonl empty or not found"}))
            return

        last = json.loads(lines[-1])
        static_limits = last.get("static_limits") or {}
        dynamic_usage = last.get("dynamic_usage") or {}

        # 2.2 生成空间感描述
        cpu_logical_cores = static_limits.get("cpu_logical_cores", 0)
        cpu_physical_cores = static_limits.get("cpu_physical_cores", 0)
        memory_total_bytes = static_limits.get("memory_total_bytes", 0)
        disk_total_bytes = static_limits.get("disk_total_bytes", 0)
        memory_used_bytes = dynamic_usage.get("memory_used_bytes", 0)
        memory_percent = dynamic_usage.get("memory_percent", 0)
        disk_percent = dynamic_usage.get("disk_percent", 0)
        cpu_percent = dynamic_usage.get("cpu_percent", 0)

        memory_total_gb = memory_total_bytes / (1024 ** 3)
        memory_used_gb = memory_used_bytes / (1024 ** 3)
        disk_total_gb = disk_total_bytes / (1024 ** 3)

        space_description = (
            f"洛神所在物理空间：CPU {cpu_logical_cores}逻辑核/{cpu_physical_cores}物理核；"
            f"内存 {memory_used_gb:.1f}GB / {memory_total_gb:.1f}GB（{memory_percent}%）；"
            f"磁盘已用 {disk_percent}%；当前CPU占用 {cpu_percent}%。"
        )

        # 2.3 生成空间感知记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "space_description": space_description,
            "source": "spatial_awareness",
        }

        # 2.4 追加写入 spatial_awareness_log.jsonl
        with open('spatial_awareness_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('spatial_awareness_log.jsonl', 'rb') as f:
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
            "file": "spatial_awareness_log.jsonl",
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
