#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 物理状态日志写入模块 physical_sensor_step4.py"""
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

        static_limits = {
            "cpu_logical_cores": psutil.cpu_count(logical=True),
            "cpu_physical_cores": psutil.cpu_count(logical=False),
            "memory_total_bytes": psutil.virtual_memory().total,
            "disk_total_bytes": psutil.disk_usage('/').total,
        }

        dynamic_usage = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "process_cpu_percent": proc.cpu_percent(interval=0.1),
            "memory_used_bytes": psutil.virtual_memory().used,
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "process_runtime_seconds": time.time() - proc.create_time(),
        }

        memory_total = static_limits["memory_total_bytes"]
        disk_total = static_limits["disk_total_bytes"]
        memory_remaining_ratio = 1 - (dynamic_usage["memory_used_bytes"] / memory_total)
        cpu_remaining_ratio = 1 - (dynamic_usage["cpu_percent"] / 100)
        disk_remaining_ratio = 1 - (dynamic_usage["disk_percent"] / 100)
        danger_level = 1 - min(memory_remaining_ratio, cpu_remaining_ratio, disk_remaining_ratio)

        if danger_level > 0.8:
            status = "critical"
        elif danger_level > 0.6:
            status = "warning"
        else:
            status = "normal"

        result = {
            "schema_version": 1,
            "timestamp": time.time(),
            "static_limits": static_limits,
            "dynamic_usage": dynamic_usage,
            "computed": {
                "memory_remaining_ratio": memory_remaining_ratio,
                "cpu_remaining_ratio": cpu_remaining_ratio,
                "disk_remaining_ratio": disk_remaining_ratio,
                "danger_level": danger_level,
                "status": status,
            }
        }

        with open('physical_state.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')

        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(0)


if __name__ == "__main__":
    main()
