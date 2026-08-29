#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 人脑到AI零件映射文件初始化模块 brain_component_map_init.py"""
import hashlib
import json
import time

MAP_CONTENT = {
    "schema_version": 1,
    "module": "brain_component_map",
    "version": 1,
    "purpose": "将人脑说法映射为洛神系统的AI物理零件，避免概念歧义。仅用于设计讨论与工程对齐，不作为运行逻辑。",
    "mappings": [
        {
            "brain_term": "海马体（记忆）",
            "component_term": "文件存储 / 数据库",
            "existing_impl": [
                "context_cache.jsonl",
                "memory_points.jsonl",
                "gene_pool.jsonl"
            ]
        },
        {
            "brain_term": "前额叶（决策）",
            "component_term": "推理引擎 / 大模型调用",
            "existing_impl": [
                "luoshen_main.py",
                "real_interaction_test.py"
            ]
        },
        {
            "brain_term": "感官（望闻问切）",
            "component_term": "输入接口 / 监测脚本",
            "existing_impl": [
                "integrity_monitor_v2.py",
                "physical_pipeline.py"
            ]
        },
        {
            "brain_term": "运动皮层（执行）",
            "component_term": "执行器 / API调用",
            "existing_impl": [
                "treatment_apply.py",
                "repair_event.py"
            ]
        },
        {
            "brain_term": "神经脉络",
            "component_term": "数据流 / 哈希链",
            "existing_impl": [
                "hash_chain_v2.log"
            ]
        },
        {
            "brain_term": "针灸穴位",
            "component_term": "测试探针 / 最小刺激点",
            "existing_impl": [
                "minimal_stimulus_test.py",
                "robustness_test.py"
            ]
        }
    ],
    "note": "本文件不改变任何现有模块的命名与逻辑，仅作为概念映射记录。"
}


def main():
    try:
        # 2.1 创建 brain_component_map.json（允许覆盖）
        content = json.dumps(MAP_CONTENT, ensure_ascii=False, indent=2) + "\n"
        with open('brain_component_map.json', 'w', encoding='utf-8') as f:
            f.write(content)

        # 2.2 计算 md5
        with open('brain_component_map.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 2.3 读取哈希链最后一条 record_hash 作为 prev_hash
        try:
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                chain_lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

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
            "file": "brain_component_map.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.4 标准输出
        print(content.rstrip('\n'))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
