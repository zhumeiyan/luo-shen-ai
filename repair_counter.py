#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 修复积分记录与报警模块 repair_counter.py"""
import hashlib
import json
import time


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return [json.loads(line) for line in lines]


def main():
    try:
        # 2.1 读取医院修复积分规则
        try:
            with open('hospital_rules/repair_credits.json', 'r', encoding='utf-8') as f:
                rules = json.load(f)
        except FileNotFoundError:
            print(json.dumps({"error": "repair_credits.json not found"}))
            return

        thresholds = rules["items"]["thresholds"]
        short_window_hours = thresholds.get("short_window_hours")
        short_window_max = thresholds.get("short_window_max")
        short_window_action = thresholds.get("short_window_action")
        daily_window_hours = thresholds.get("daily_window_hours")
        daily_window_warn = thresholds.get("daily_window_warn")
        daily_window_warn_action = thresholds.get("daily_window_warn_action")
        daily_window_stop = thresholds.get("daily_window_stop")
        daily_window_stop_action = thresholds.get("daily_window_stop_action")

        # 2.2 读取历史修复记录（不存在则视为空）
        records = []
        try:
            with open('repair_count_log.jsonl', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except FileNotFoundError:
            pass

        # 2.3 统计修复次数
        now = time.time()
        short_count = 0
        daily_count = 0
        for rec in records:
            ts = rec.get("timestamp")
            if ts is None:
                continue
            if now - ts < short_window_hours * 3600:
                short_count += 1
            if now - ts < daily_window_hours * 3600:
                daily_count += 1

        # 2.4 判断报警动作
        if short_count >= short_window_max:
            triggered_action = short_window_action
        elif daily_count >= daily_window_stop:
            triggered_action = daily_window_stop_action
        elif daily_count >= daily_window_warn:
            triggered_action = daily_window_warn_action
        else:
            triggered_action = "normal"

        # 2.5 生成修复计数报告
        report = {
            "schema_version": 1,
            "timestamp": now,
            "short_count": short_count,
            "daily_count": daily_count,
            "triggered_action": triggered_action,
            "thresholds": {
                "short_window_max": short_window_max,
                "daily_window_warn": daily_window_warn,
                "daily_window_stop": daily_window_stop,
            },
        }

        # 2.6 追加写入 repair_count_log.jsonl
        with open('repair_count_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(report, ensure_ascii=False) + '\n')

        # 2.7 计算 md5 并追加哈希链
        with open('repair_count_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            chain_records = load_chain_records('hash_chain_v2.log')
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        prev_hash = None
        if chain_records:
            prev_hash = chain_records[-1].get("record_hash")

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "repair_count_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.8 标准输出
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
