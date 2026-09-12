#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 中西结合治疗方案生成模块 treatment_integrative.py"""
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

        # 2.3 读取哈希链
        records = load_chain_records('hash_chain_v2.log')

        def expected_hash(file_name):
            for rec in reversed(records):
                if rec.get("file") == file_name:
                    return rec.get("file_hash")
            return None

        # 2.4 生成西医精准方案
        precise_diagnosis = []
        for issue in issue_list:
            target_file = issue.get("file")
            expected = expected_hash(target_file) if target_file else None
            if expected is None:
                precise_action = "标记为无参照文件，需人工核查"
            else:
                precise_action = "对该文件重新进行哈希补录"
            precise_diagnosis.append({
                "target_file": target_file,
                "expected_state": expected,
                "precise_action": precise_action,
            })

        issue_count = len(issue_list)

        # 2.5 生成中医整体方案
        if grade in ("warning", "critical"):
            prevention = "建议增加健康检查频率"
        else:
            prevention = "建议维持当前检查频率"

        from collections import Counter
        type_counts = Counter(item.get("event_type") for item in issue_list)
        repeated = any(count >= 2 for count in type_counts.values())
        if repeated:
            pattern_classification = "反复性问题"
        else:
            pattern_classification = "偶发问题"

        prescription = {
            "chief_action": "对受影响文件进行哈希补录",
            "deputy_action": "重新验证链完整性",
            "assistant_action": "暂停相关自动任务",
            "guide_action": "将本次治疗写入审计日志",
        }
        rollback_plan = "执行前创建回滚点"
        stimulus_test = "对受影响文件执行最小刺激读取测试"

        # 2.6 生成中西结合治疗方案 JSON
        combined_actions = ["创建回滚点"]
        if precise_diagnosis:
            combined_actions.append(precise_diagnosis[0].get("precise_action"))
        combined_actions.append("重新验证链完整性")
        combined_actions.append("运行健康评分验证")

        treatment_plan = {
            "schema_version": 1,
            "timestamp": time.time(),
            "grade": grade,
            "issue_count": issue_count,
            "western_plan": {
                "precise_diagnosis": precise_diagnosis,
            },
            "chinese_plan": {
                "prevention": prevention,
                "pattern_classification": pattern_classification,
                "prescription": prescription,
                "rollback_plan": rollback_plan,
                "stimulus_test": stimulus_test,
            },
            "combined_actions": combined_actions,
        }

        # 2.7 追加写入 treatment_plans.jsonl
        with open('treatment_plans.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(treatment_plan, ensure_ascii=False) + '\n')

        # 2.8 计算 md5 并追加哈希链
        with open('treatment_plans.jsonl', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

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

        # 2.9 标准输出
        print(json.dumps(treatment_plan, indent=2, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
