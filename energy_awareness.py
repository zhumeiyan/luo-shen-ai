#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 能量感知模块 energy_awareness.py"""
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

        cpu_percent = dynamic_usage.get("cpu_percent", 0)
        memory_percent = dynamic_usage.get("memory_percent", 0)
        cpu_physical_cores = static_limits.get("cpu_physical_cores", 0)
        memory_total_bytes = static_limits.get("memory_total_bytes", 0)

        # 2.2 估算当前能耗
        cpu_power = cpu_physical_cores * 5.0 * (cpu_percent / 100.0)
        memory_power = (memory_total_bytes / (1024 ** 3)) * 0.5 * (memory_percent / 100.0)
        total_power = cpu_power + memory_power

        # 2.3 计算电费感
        cost_per_hour = total_power / 1000.0 * 0.6
        cost_per_day = cost_per_hour * 24

        # 2.4 生成能量描述字符串
        description = (
            f"洛神当前功耗约 {total_power:.1f}W，"
            f"电费约 {cost_per_hour:.4f}元/小时，"
            f"日用电费约 {cost_per_day:.2f}元。"
        )

        # 2.5 生成能量感知记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "power_watt": total_power,
            "cost_per_hour": cost_per_hour,
            "cost_per_day": cost_per_day,
            "description": description,
            "source": "energy_awareness",
        }

        # 2.6 追加写入 energy_awareness_log.jsonl
        with open('energy_awareness_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('energy_awareness_log.jsonl', 'rb') as f:
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
            "file": "energy_awareness_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
