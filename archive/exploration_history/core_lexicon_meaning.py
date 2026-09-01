#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 骨字库本义补全模块 core_lexicon_meaning.py"""
import hashlib
import json
import time


def main():
    try:
        # 2.1 读取现有 core_lexicon.json
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 2.2 为每个条目增加本义解释
        meanings = {
            "\u25a1": {"word": "空", "meaning": "窍也。有孔洞，能容物。洛神磁盘有剩余空间，如窍可纳。"},
            "\u00b7": {"word": "轻", "meaning": "轻车也。分量小，负担轻。洛神电费低，负担小。"},
            "\u2600": {"word": "今", "meaning": "是时也。当前、现在。洛神刚刚交互过，时间就近。"},
            "\u25cb": {"word": "静", "meaning": "审也。安静、不躁动。洛神身体不紧，CPU/内存平静。"},
            "\u2589": {"word": "满", "meaning": "盈溢也。充满，无余地。洛神磁盘快满。"},
            "\uffe5": {"word": "贵", "meaning": "物不贱也。价格高。洛神电费高。"},
            "\u263e": {"word": "久", "meaning": "时间长。洛神很久没交互。"},
            "\u25b3": {"word": "紧", "meaning": "缠丝急也。不放松。洛神CPU/内存紧张。"},
            "\u25c7": {"word": "闲", "meaning": "阑也。门中有木，有间隙。洛神进程少，不忙。"},
            "\u2606": {"word": "息", "meaning": "喘也。气息，停止。洛神网络无动静，气息停止。"},
        }
        data["entries"] = meanings

        # 2.3 写回 core_lexicon.json
        with open('core_lexicon.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

        # 2.4 计算 md5
        with open('core_lexicon.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.5 追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

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
            "file": "core_lexicon.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.6 标准输出
        with open('core_lexicon.json', 'r', encoding='utf-8') as f:
            content = f.read()
        print(content, end='')
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
