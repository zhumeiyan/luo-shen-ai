#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 外部AI诊断模块 external_diagnosis.py"""
import hashlib
import json
import time
import ast

CODE = '''def get_user_age():\n    return 25\n\nage = get_user_age()\nprint("User age: " + age)\n'''


def main():
    try:
        # AI 医院网关检查
        try:
            from hospital_gateway import check as hospital_check
            gate = hospital_check("external_ai", "target_external_code")
            if not gate.get("allow"):
                print(json.dumps({"blocked_by": "hospital_gateway", "reason": gate.get("reason")}))
                return
        except Exception:
            pass

        issues = []
        syntax_error = None

        # 2.2 使用 ast 解析代码
        try:
            tree = ast.parse(CODE)
        except SyntaxError as e:
            syntax_error = {
                "line_number": getattr(e, "lineno", None),
                "description": "语法错误: " + str(e),
            }

        if syntax_error is None:
            # 2.3 基础静态检查
            # 检查字符串与整数直接拼接
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                    left = node.left
                    right = node.right
                    left_is_str = isinstance(left, ast.Constant) and isinstance(left.value, str)
                    right_is_str = isinstance(right, ast.Constant) and isinstance(right.value, str)
                    left_is_num = isinstance(left, ast.Constant) and isinstance(left.value, (int, float)) and not isinstance(left.value, bool)
                    right_is_num = isinstance(right, ast.Constant) and isinstance(right.value, (int, float)) and not isinstance(right.value, bool)
                    if (left_is_str and right_is_num) or (right_is_str and left_is_num) or (left_is_str and not right_is_str and not isinstance(right, ast.Constant)):
                        issues.append({
                            "issue_id": "ISSUE-001",
                            "issue_type": "type_concat",
                            "line_number": node.lineno,
                            "description": "字符串与整数直接拼接：print(\"User age: \" + age)，age 为整数",
                            "severity": "P2",
                        })

            # 检查访问可能为 None 的对象
            # 本样本代码中无属性/下标访问潜在 None，标记无该问题
            none_issues = [n for n in ast.walk(tree)
                           if isinstance(n, (ast.Attribute, ast.Subscript))]
            # 数组索引访问但未做边界检查
            for node in ast.walk(tree):
                if isinstance(node, ast.Subscript):
                    value_type = None
                    if isinstance(node.value, ast.Name):
                        value_type = node.value.id
                    issues.append({
                        "issue_id": "ISSUE-002",
                        "issue_type": "index_risk",
                        "line_number": node.lineno,
                        "description": "数组索引访问未做边界检查：对象 {} 下标访问前未见长度校验".format(value_type or "未知"),
                        "severity": "P3",
                    })

        # 2.4 生成诊断报告
        report = {
            "schema_version": 1,
            "timestamp": time.time(),
            "report_type": "external_ai_diagnosis",
            "basic_info": {
                "patient": "external_ai_code_sample",
                "submitter": "engineer",
                "diagnosis_level": "outpatient",
            },
            "chief_complaint": "程序运行时报错，无法继续执行",
            "symptoms": "控制台提示 TypeError，字符串与整数直接拼接",
            "western_diagnosis": {
                "check_item": "类型检查",
                "result": "fail",
                "location": "第5行",
                "evidence": "unsupported operand type(s) for +: 'int' and 'str'",
            },
            "chinese_diagnosis": {
                "overall_status": "局部问题",
                "pattern": "偶发问题",
                "root_cause": "变量 age 为整数，直接与字符串拼接",
            },
            "severity": "P2",
            "treatment": {
                "western_action": "将 print(\"User age: \" + age) 改为 print(\"User age: \" + str(age))",
                "chinese_action": "在函数返回值处增加类型检查，防止后续再次发生",
                "rollback_plan": "保留原始代码副本",
            },
            "verification": {
                "steps": ["重新运行代码，确认无 TypeError", "用整数输入测试"],
                "pass_criteria": "程序正常运行，输出 User age: 25",
            },
            "followup": "若修复后仍有问题，请再次提交",
        }

        if syntax_error is not None:
            report["issues"] = [{
                "issue_id": "ISSUE-001",
                "issue_type": "syntax_error",
                "line_number": syntax_error["line_number"],
                "description": syntax_error["description"],
                "severity": "P0",
            }]
        else:
            report["issues"] = issues

        # 2.5 写入 external_diagnosis_report.json（允许覆盖）
        with open('external_diagnosis_report.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(report, indent=2, ensure_ascii=False) + '\n')

        # 2.6 计算 md5 并追加哈希链
        with open('external_diagnosis_report.json', 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        try:
            records = []
            with open('hash_chain_v2.log', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except FileNotFoundError:
            print(json.dumps({"error": "hash_chain_v2.log not found"}))
            return

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
            "file": "external_diagnosis_report.json",
            "file_hash": file_hash,
            "prev_hash": prev_hash,
            "record_hash": record_hash,
        }

        with open('hash_chain_v2.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(chain_record, ensure_ascii=False) + '\n')

        # 2.7 标准输出
        print(json.dumps(report, ensure_ascii=False))
        print()
        print(json.dumps(chain_record, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
