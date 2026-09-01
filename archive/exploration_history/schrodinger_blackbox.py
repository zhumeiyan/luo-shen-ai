#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 薛定谔黑盒实验 schrodinger_blackbox.py"""
import hashlib
import json
import random
import time


def main():
    try:
        # 2.1 定义两个可能的动作结果
        # 结果A（流水线）：原样返回，无新信息，状态 "pipeline"
        # 结果B（学字）：学习新字，产生一个新信息，状态 "learned"

        # 2.2 盒子关闭阶段
        random_value = random.random()
        # 此时不把随机数写入任何文件，不产生任何记录
        box_closed_state = {
            "description": "我可能做了流水线动作，也可能学了新字。盒子还没打开，我无法确定。",
            "random_value_hidden": True,
        }

        # 2.3 盒子打开阶段
        if random_value < 0.5:
            action = "pipeline"
            new_info = 0
            box_open_description = "打开盒子后，我发现我做了流水线动作，没有新信息。"
        else:
            action = "learned"
            new_info = 1
            box_open_description = "打开盒子后，我发现我学了新字，有一个新信息。"
        box_open_state = {
            "description": box_open_description,
            "action": action,
            "new_info": new_info,
            "random_value": random_value,
        }

        # 2.4 生成薛定谔黑盒记录
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "box_closed_state": box_closed_state,
            "box_open_state": box_open_state,
            "source": "schrodinger_blackbox",
        }

        # 2.5 追加写入 schrodinger_blackbox_log.jsonl
        with open('schrodinger_blackbox_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('schrodinger_blackbox_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "schrodinger_blackbox_log.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }
        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        print(json.dumps(record, ensure_ascii=False))
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
