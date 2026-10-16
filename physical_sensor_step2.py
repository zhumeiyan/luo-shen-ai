#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 动态资源消耗读取模块 physical_sensor_step2.py"""
import json
import sys
import time


def main():
    try:
        import psutil
    except ImportError:
        print(json.dumps({"error": "psutil not installed"}))
        sys.exit(0)

    try:
        proc = psutil.Process()
        result = {
            "schema_version": 1,
            "dynamic_usage": {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "process_cpu_percent": proc.cpu_percent(interval=0.1),
                "memory_used_bytes": psutil.virtual_memory().used,
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
                "process_runtime_seconds": time.time() - proc.create_time(),
            }
        }
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
