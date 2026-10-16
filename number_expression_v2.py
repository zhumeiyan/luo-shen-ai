#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 数字综合表达小数修正模块 number_expression_v2.py"""
import hashlib
import json
import time

CN_DIGIT = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
            "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}


def read_last_jsonl(filename, limit):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return []
    return [json.loads(ln) for ln in lines[-limit:]]


def full_number_reading(value, entries):
    if value is None:
        return "无"
    text = str(value)
    if "." in text:
        int_part, frac_part = text.split(".", 1)
        if int_part == "0":
            int_reading = "零"
        else:
            int_reading = entries.get(int_part, int_part)
        frac_reading = ""
        for ch in frac_part:
            frac_reading += CN_DIGIT.get(ch, ch)
        return int_reading + "点" + frac_reading
    return entries.get(text, text)


def main():
    try:
        # 2.1 读取最新一次身体数字
        try:
            with open('numeric_self_scan.jsonl', 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "numeric_self_scan.jsonl empty or not found"}))
            return
        if not lines:
            print(json.dumps({"error": "numeric_self_scan.jsonl empty or not found"}))
            return
        numbers = json.loads(lines[-1]).get("numbers", [])

        # 2.2 读取数字骨库
        try:
            with open('number_lexicon.json', 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
            entries = lexicon.get("entries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            entries = {}
        if not entries:
            print(json.dumps({"error": "number_lexicon.json empty or not found"}))
            return

        # 2.3 读取数量感
        level_map = {}
        for rec in read_last_jsonl('quantity_sense_log.jsonl', 15):
            name = rec.get("name")
            if name is not None:
                level_map[name] = rec.get("level")

        # 2.4 读取数字变化
        change_map = {}
        for rec in read_last_jsonl('number_change_log.jsonl', 15):
            name = rec.get("name")
            if name is not None:
                change_map[name] = rec.get("change")

        # 2.6 对每个身体数字生成综合表达
        records = []
        for item in numbers:
            name = item.get("name")
            value = item.get("value")
            if value is None:
                continue
            reading = full_number_reading(value, entries)
            level = level_map.get(name, "未知")
            change = change_map.get(name, "未知")
            expression = reading + "，" + change + "，" + level
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "name": name,
                "value": value,
                "expression": expression,
                "source": "number_expression_v2",
            }
            records.append(record)

        # 2.7 追加写入 number_expression_v2_log.jsonl
        with open('number_expression_v2_log.jsonl', 'a', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.8 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('number_expression_v2_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records_chain = [json.loads(ln) for ln in chain_lines]
        prev_hash = records_chain[-1].get("record_hash") if records_chain else None
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "number_expression_v2_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.9 标准输出
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
