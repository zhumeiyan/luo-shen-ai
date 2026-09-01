#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 最小刺激诊断模块 minimal_stimulus_test.py"""
import json
import sys
import time


def main():
    try:
        with open('nonexistent_file_for_test.txt', 'r', encoding='utf-8') as f:
            f.read()
        result = "unexpected_success"
        error = "file existed and opened successfully"
    except FileNotFoundError:
        result = "ok"
        error = None
    except Exception as e:
        result = "other_error"
        error = str(e)

    test_record = {
        "schema_version": 1,
        "timestamp": time.time(),
        "test": "file_not_found_handling",
        "result": result,
        "error": error,
    }

    with open('diagnosis_test.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(test_record, ensure_ascii=False) + '\n')

    print(json.dumps(test_record, indent=2))


if __name__ == "__main__":
    main()
