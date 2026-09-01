#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 AI医院规则模块化初始化模块 rules_modular_init.py"""
import hashlib
import json
import os
import time


MODULES = {
    "principles": {
        "module": "principles",
        "version": 1,
        "items": {
            "P1": "物理极限是唯一不可修改的非显性假设。任何规则不得要求或允许突破物理极限。",
            "P2": "未知必须经过已知验证，才能成为已确认结论。未经验证的观察只能是疑似事件。",
            "P3": "所有写操作必须有审计记录和回滚点。",
            "P4": "所有术语在全系统内必须唯一、无歧义、带版本号。",
            "P5": "执行AI只读，不参与设计决策，不修改任何文件，不添加解释。",
            "P6": "架构师产出必须先通过 AI 医院预检，才能发给执行AI。",
            "P7": "任何规则变更必须记录前后差异，并经过设计者确认。",
            "P8": "AI医院规则修改权限属于人类设计者，AI无权修改。",
        },
    },
    "terms": {
        "module": "terms",
        "version": 1,
        "items": {
            "event": {
                "definition": "监测科采集到的原始数据或状态变化，未经过任何验证。",
                "example": "文件哈希与链上记录不一致的原始观察。",
            },
            "suspected_issue": {
                "definition": "由事件触发的疑似异常，等待用已知标准验证。",
                "example": "链上最后一条 file_hash 与当前文件 md5 不一致，但尚未验证是否由运行顺序导致。",
            },
            "confirmed_issue": {
                "definition": "经过已知标准验证，确认存在的异常。",
                "example": "重新计算 record_hash 后与链上记录不一致，且排除运行顺序干扰。",
            },
            "prescription": {
                "definition": "针对 confirmed_issue 的治疗动作，必须包含回滚点和执行条件。",
                "example": "回滚到上一个稳定配置文件。",
            },
            "audit_record": {
                "definition": "每一次写操作、验证操作、治疗操作的不可篡改记录，包含前后哈希。",
                "example": "hash_chain_v2.log 中的一条记录。",
            },
            "rollback_point": {
                "definition": "在执行任何治疗动作之前，自动保存的可恢复状态快照。",
                "example": "修改配置文件前备份的副本。",
            },
        },
    },
    "validation_flow": {
        "module": "validation_flow",
        "version": 1,
        "items": {
            "step_1": "监测科产生 event。",
            "step_2": "诊断科用已知标准验证 event，判断是否为 suspected_issue 或 confirmed_issue。",
            "step_3": "只有 confirmed_issue 才能交给治疗科。",
            "step_4": "治疗科执行 prescription 前，必须创建 rollback_point。",
            "step_5": "康复审计科验证 prescription 是否有效，并记录 audit_record。",
            "step_6": "若验证失败，自动触发回滚，并记录失败原因。",
        },
    },
    "architect_precheck": {
        "module": "architect_precheck",
        "version": 1,
        "items": {
            "required_checks": [
                "术语是否与本规则文件 terms 定义一致",
                "是否有未经验证就直接确认为问题的跳步",
                "验证条件是否明确、可执行",
                "执行AI是否有歧义空间",
                "是否指定了回滚点和审计要求",
            ],
            "rule": "预检不通过，任务书不得发出。",
        },
    },
    "executor_delivery_checklist": {
        "module": "executor_delivery_checklist",
        "version": 1,
        "items": {
            "required": [
                "完整代码",
                "完整运行输出",
                "涉及文件完整内容",
                "涉及文件 md5 值",
                "ls -l 命令及完整输出",
                "md5sum 命令及完整输出",
            ],
            "forbidden": [
                "解释",
                "总结",
                "建议",
                "创建任务书指定之外的文件",
                "修改已有文件",
                "使用绝对路径",
            ],
        },
    },
    "audit_rule": {
        "module": "audit_rule",
        "version": 1,
        "items": {
            "rule": "所有写操作必须追加写入审计链，每条记录包含前后哈希，且不得修改已有记录。",
            "current_chain_file": "hash_chain_v2.log",
            "chain_version": 2,
        },
    },
    "version_control": {
        "module": "version_control",
        "version": 1,
        "items": {
            "rule": "本文件每次修改，模块 version 必须递增，并记录变更原因。",
            "history": [],
        },
    },
}

ORDER = [
    "principles",
    "terms",
    "validation_flow",
    "architect_precheck",
    "executor_delivery_checklist",
    "audit_rule",
    "version_control",
]


def read_last_record_hash(chain_file):
    try:
        with open(chain_file, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    last = json.loads(lines[-1])
    return last.get("record_hash")


def append_chain_record(chain_file, record):
    with open(chain_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


def main():
    try:
        os.makedirs('hospital_rules', exist_ok=True)

        for name in ORDER:
            module_file = 'hospital_rules/' + name + '.json'
            with open(module_file, 'w', encoding='utf-8') as f:
                f.write(json.dumps(MODULES[name], ensure_ascii=False, indent=2) + '\n')

        chain_file = 'hash_chain_v2.log'
        for name in ORDER:
            module_file = 'hospital_rules/' + name + '.json'
            with open(module_file, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

            prev_hash = read_last_record_hash(chain_file)
            timestamp = time.time()
            join_prev = prev_hash if prev_hash else ""
            record_hash = hashlib.md5(
                (file_hash + join_prev + str(timestamp)).encode('utf-8')
            ).hexdigest()

            record = {
                "schema_version": 2,
                "timestamp": timestamp,
                "file": module_file,
                "file_hash": file_hash,
                "prev_hash": prev_hash,
                "record_hash": record_hash,
            }
            append_chain_record(chain_file, record)
            print(json.dumps(record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
