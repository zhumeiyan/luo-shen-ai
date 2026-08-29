#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 身体数字读出模块 number_reading.py"""
import hashlib
import json
import time

CN = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
      "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}


def int_reading(n):
    """0-999 整数转中文读法，大于999保留原数字字符串。"""
    if n > 999:
        return str(n)
    if n == 0:
        return "零"
    result = ""
    hundreds = n // 100
    rest = n % 100
    if hundreds:
        result += CN[str(hundreds)] + "百"
        if rest == 0:
            return result
        if rest < 10:
            result += "零"
    tens = rest // 10
    ones = rest % 10
    if tens:
        if tens == 1 and hundreds == 0:
            result += "十"
        else:
            result += CN[str(tens)] + "十"
    if ones:
        result += CN[str(ones)]
    return result


def to_reading(value):
    if value is None:
        return "无"
    text = str(value)
    if "." in text:
        int_part, frac_part = text.split(".", 1)
        # 若小数部分全为0，视为整数
        if set(frac_part) == {"0"}:
            return int_reading(int(int_part))
        reading = int_reading(int(int_part)) + "点"
        for ch in frac_part:
            reading += CN.get(ch, ch)
        return reading
    return int_reading(int(text))


def main():
    try:
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

        records = []
        for item in numbers:
            name = item.get("name")
            value = item.get("value")
            record = {
                "schema_version": 1,
                "timestamp": time.time(),
                "name": name,
                "value": value,
                "reading": to_reading(value),
                "source": "number_reading",
            }
            records.append(record)

        # 2.4 追加写入 number_reading_log.jsonl
        with open('number_reading_log.jsonl', 'a', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.5 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

        with open('number_reading_log.jsonl', 'rb') as f:
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
            "file": "number_reading_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
