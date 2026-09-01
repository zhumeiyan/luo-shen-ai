#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 静态物理极限读取模块 physical_sensor_step1.py"""
import json
import sys


def main():
    try:
        import psutil
    except ImportError:
        print(json.dumps({"error": "psutil not installed"}))
        sys.exit(0)

    try:
        result = {
            "schema_version": 1,
            "static_limits": {
                "cpu_logical_cores": psutil.cpu_count(logical=True),
                "cpu_physical_cores": psutil.cpu_count(logical=False),
                "memory_total_bytes": psutil.virtual_memory().total,
                "disk_total_bytes": psutil.disk_usage('/').total,
            }
        }
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
