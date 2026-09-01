#!/usr/bin/env python3
"""
environment_tick 后台启动脚本。
保持主线程存活，environment_tick 在后台每 15 分钟执行一次。
"""
import sys, time, json
sys.path.insert(0, ".")

from living_engine import (
    start_environment_ticks,
    _ENV_TICK_RUNNING,
    _ENV_TICK_THREAD,
    environment_tick,
)

# 重置 tick 时间，让下一次能触发
from living_engine import cold_start_if_needed, _save_json_atomic
mem = cold_start_if_needed()
mem["__meta"]["last_environment_tick"] = 0
_save_json_atomic("active_memory/active_memory.json", mem)

INTERVAL = 900  # 15 分钟
result = start_environment_ticks(INTERVAL)
print(json.dumps(result, ensure_ascii=False))

# 保持主线程存活，等待后台循环
try:
    while _ENV_TICK_RUNNING:
        time.sleep(60)
except KeyboardInterrupt:
    print("Shutting down...")
