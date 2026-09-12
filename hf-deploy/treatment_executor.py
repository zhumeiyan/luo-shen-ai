#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 治疗手段生成模块 treatment_executor.py"""
import hashlib
import json
import time


def load_chain_records(chain_file):
    with open(chain_file, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return [json.loads(line) for line in lines]


def read_last_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    try:
        # 2.1 读取诊断结果
        try:
            diag_last = read_last_jsonl('diagnosis_results.jsonl')
        except FileNotFoundError:
            print(json.dumps({"error": "diagnosis_results.jsonl not found"}))
            return
        if diag_last is None:
            diag_list = []
        else:
            diag_list = diag_last.get("diagnosis_results", [])
        issue_list = [item for item in diag_list if item.get("diagnosis") == "confirmed_issue"]

        # 2.2 读取健康评分
        try:
            score_last = read_last_jsonl('health_score.jsonl')
        except FileNotFoundError:
            print(json.dumps({"error": "health_score.jsonl not found"}))
            return
        if score_last is None:
            total_score = 0
            grade = "unknown"
        else:
            total_score = score_last.get("total_score", 0)
            grade = score_last.get("grade", "unknown")

        issue_count = len(issue_list)

        # 2.3 按中医五层生成治疗方案
        # 第一层：治未病
        if grade in ("warning", "critical"):
            prevention = "建议增加健康检查频率"
        else:
            prevention = "建议维持当前检查频率"

        # 第二层：辨证施治
        from collections import Counter
        type_counts = Counter(item.get("event_type") for item in issue_list)
        repeated = any(count >= 2 for count in type_counts.values())
        if repeated:
            pattern_classification = "反复性问题"
        else:
            pattern_classification = "偶发问题"

        # 第三层：整体观（组合处方）
        prescription = {
            "chief_action": "对受影响文件进行哈希补录",
            "deputy_action": "重新验证链完整性",
            "assistant_action": "暂停相关自动任务",
            "guide_action": "将本次治疗写入审计日志",
        }

        # 第四层：扶正祛邪
        rollback_plan = "执行前创建回滚点"

        # 第五层：针灸疗法（最小刺激测试，只读不修改）
        stimulus_test = "对受影响文件执行最小刺激读取测试"
        for issue in issue_list:
            target_file = issue.get("file")
            if target_file:
                try:
                    with open(target_file, 'rb') as f:
                        f.read(1)
                    issue["stimulus"] = "responsive"
                except FileNotFoundError:
                    issue["stimulus"] = "inactive"
                except Exception:
                    issue["stimulus"] = "inactive"

        # 2.4 生成治疗建议 JSON
        treatment_plan = {
            "schema_version": 1,
            "timestamp": time.time(),
            "grade": grade,
            "issue_count": issue_count,
            "principles_applied": {
                "prevention": prevention,
                "pattern_classification": pattern_classification,
                "prescription": prescription,
                "rollback_plan": rollback_plan,
                "stimulus_test": stimulus_test,
            },
            "suggested_actions": [
                "创建回滚点",
                "对受影响文件进行哈希补录",
                "重新验证链完整性",
                "运行健康评分验证",
            ],
        }

        # 2.5 追加写入 treatment_plans.jsonl
        with open('treatment_plans.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(treatment_plan, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        with open('treatment_plans.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        records = load_chain_records('hash_chain_v2.log')
        prev_hash = None
        if records:
            prev_hash = records[-1].get("record_hash")

        timestamp = time.time()
        join_prev = prev_hash if prev_hash else ""
        record_hash = hashlib.md5(
            (file_hash + join_prev + str(timestamp)).encode('utf-8')
        ).hexdigest()

        chain_record = {
            "schema_version": 2,
            "timestamp": timestamp,
            "file": "treatment_plans.jsonl",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        print(json.dumps(treatment_plan, indent=2, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
