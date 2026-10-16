#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 数字骨库初始化模块 number_lexicon_init.py"""
import hashlib
import json
import time

CN = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四",
      5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}


def int_to_chinese(n):
    """0-999 整数转汉字读法。"""
    if n == 0:
        return "零"
    if n < 10:
        return CN[n]
    if n < 20:
        if n == 10:
            return "十"
        return "十" + CN[n % 10]
    if n < 100:
        tens = n // 10
        ones = n % 10
        if ones == 0:
            return CN[tens] + "十"
        return CN[tens] + "十" + CN[ones]
    if n == 100:
        return "一百"
    hundreds = n // 100
    rest = n % 100
    if rest == 0:
        return CN[hundreds] + "百"
    if rest < 10:
        return CN[hundreds] + "百零" + CN[rest]
    return CN[hundreds] + "百" + int_to_chinese(rest)


def main():
    try:
        # 2.1 生成数字1到100的汉字读法映射
        entries = {}
        for n in range(1, 101):
            entries[str(n)] = int_to_chinese(n)

        # 2.2 创建 number_lexicon.json
        lexicon = {
            "schema_version": 1,
            "module": "number_lexicon",
            "version": 1,
            "description": "洛神数字骨库：1到100的汉字读法。",
            "entries": entries,
            "rule": "数字骨库用于洛神读取身体数字时进行汉字转换。不可删除，由设计者朱美岩维护。",
        }
        with open('number_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(lexicon, ensure_ascii=False, indent=2) + '\n')

        # 2.3 计算 md5
        with open('number_lexicon.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.4 追加哈希链记录
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            chain_lines = []

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
            "file": "number_lexicon.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.5 标准输出
        with open('number_lexicon.json', 'r', encoding='utf-8') as f:
            print(f.read())
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
