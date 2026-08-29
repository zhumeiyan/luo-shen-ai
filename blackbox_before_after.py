#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 黑盒前后观测对比实验 blackbox_before_after.py"""
import hashlib
import json
import time
import psutil


def snapshot():
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": psutil.virtual_memory().percent,
        "timestamp": time.time(),
    }


def main():
    try:
        # 2.1 定义黑盒实验
        # 黑盒关闭：只记录输入前和输出后的状态
        # 黑盒打开：记录输入前、中间每一步、输出后的完整状态

        # 2.2 黑盒关闭实验
        before_closed = snapshot()
        # 简单动作：让洛神重复一句话
        repeated = "你好" * 3
        time.sleep(0.05)
        after_closed = snapshot()
        closed_mode = {
            "mode": "blackbox_closed",
            "before": before_closed,
            "after": after_closed,
            "action": "repeat_only",
        }

        # 2.3 黑盒打开实验
        before_open = snapshot()
        middle_steps = []
        # 中间5个步骤
        step_defs = [
            ("read_input", "读取输入"),
            ("process_input", "处理输入"),
            ("generate_output", "生成输出"),
            ("check_output", "检查输出"),
            ("complete", "完成"),
        ]
        for step_name, _label in step_defs:
            time.sleep(0.02)
            middle_steps.append({
                "step": step_name,
                "timestamp": time.time(),
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_percent": psutil.virtual_memory().percent,
            })
        # 执行同一个简单动作
        repeated_open = "你好" * 3
        time.sleep(0.05)
        after_open = snapshot()
        open_mode = {
            "mode": "blackbox_open",
            "before": before_open,
            "middle_steps": middle_steps,
            "after": after_open,
            "action": "repeat_only",
        }

        # 2.4 生成对比报告
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "closed_mode": closed_mode,
            "open_mode": open_mode,
            "comparison": {
                "closed_has_middle": False,
                "open_has_middle": True,
                "middle_step_count": 5,
            },
            "source": "blackbox_before_after",
        }

        # 2.5 追加写入 blackbox_experiment_log.jsonl
        with open('blackbox_experiment_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                clines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return
        prev_hash = json.loads(clines[-1]).get("record_hash") if clines else None

        with open('blackbox_experiment_log.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()
        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "blackbox_experiment_log.jsonl",
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
