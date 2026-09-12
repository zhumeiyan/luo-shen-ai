#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tick_daemon.py — 洛神认知核心时钟守护

原则：
- 每 30 秒调用一次 core.tick_step()
- 独立进程运行，不阻塞主程序
- 可读写 cognitive_core_log.jsonl
- 只有 NumPy 依赖

退出：Ctrl+C 或 SIGTERM 优雅停止。
"""

import time
import signal
import sys
import os

from cognitive_core import get_core, CognitiveCore

# ── 配置 ──────────────────────────────────────────────────────────────────────

TICK_INTERVAL = 30.0  # 秒
SEED = 42

# ── 状态 ──────────────────────────────────────────────────────────────────────

_running = True

def _handle_signal(signum, frame):
    global _running
    _running = False


def run_daemon(core: CognitiveCore = None, tick_interval: float = TICK_INTERVAL):
    """
    启动 tick 守护循环。
    
    用法：
        from tick_daemon import run_daemon
        run_daemon()  # 阻塞式
        
    或命令行：
        python tick_daemon.py
    """
    global _running
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if core is None:
        core = get_core(seed=SEED)

    print(f"[TickDaemon] 启动 — interval={tick_interval}s, seed={SEED}")
    print(f"[TickDaemon] 核心 tick_count={core.tick_count}, phase={core.phase}")
    sys.stdout.flush()

    last_tick = time.time()
    next_tick = last_tick + tick_interval

    while _running:
        now = time.time()
        if now >= next_tick:
            record = core.tick_step()
            tick = record["tick"]
            phase = record["phase"]
            error = record["error"]
            print(f"[TickDaemon] tick={tick} phase={phase} error={error:.4f} ts={now:.2f}")
            sys.stdout.flush()
            next_tick = now + tick_interval
        else:
            # 睡眠一小段时间再检查（避免忙等待）
            sleep_time = min(next_tick - now, 0.5)
            time.sleep(max(sleep_time, 0.01))

    print(f"\n[TickDaemon] 停止。总 tick={core.tick_count}, 最终 phase={core.phase}")
    sys.stdout.flush()


if __name__ == "__main__":
    run_daemon()
