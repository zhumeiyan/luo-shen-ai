#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小测试：验证 mu_core 被 S_EMA 驱动产生不可逆偏移。

设计：
- 起始点：mu_core=0.5（冷启动默认）
- 若干 tick 后，S 因环的 (N+M)/2 驱动趋向某个值
- mu_core 被 ema_S 极缓慢拉动 → 永久偏离 0.5
- 测试 A：固定环境跑 300 tick，看 mu_core 是否偏移
- 测试 B（稍后再跑）：从同一 MU 起点，换不同环境参数
"""
import sys, os, time
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from living_engine import (
    cold_start_if_needed, _save_json_atomic,
    environment_tick, _load_json,
)

def reset():
    """彻底重置 memory，确保 mu_core=0.5"""
    m = cold_start_if_needed()
    m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    if 'self_model' not in m:
        m['self_model'] = {}
    m['self_model']['ring_state'] = {'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0}
    _save_json_atomic('active_memory/active_memory.json', m)


def run_a(n_ticks=300):
    """固定环境跑 n_ticks"""
    reset()
    trail = []
    for i in range(n_ticks):
        environment_tick(force=True)
        time.sleep(0.02)
        m = _load_json('active_memory/active_memory.json')
        rs = m.get('self_model', {}).get('ring_state', {})
        climate = m.get('internal_climate', {})
        trail.append({
            'tick': i+1,
            'E': climate.get('emotion_intensity', 0),
            'T': climate.get('tension', 0),
            'N': climate.get('energy', 0),
            'M': climate.get('memory_pressure', 0),
            'S': rs.get('S', 0),
            'ema_S': rs.get('ema_S', 0),
            'mu_core': rs.get('mu_core', 0.5),
            'mu_eff': rs.get('mu_eff', 0),
        })
    return trail


def main():
    print("===== 不可逆参数漂移测试 =====")
    print("epsilon = 0.002, ema_alpha = 0.005, dt = 0.08")
    print("mu_core(0) = 0.5（冷启动重置）\n")

    trail = run_a(300)

    print(f"{'tick':>5} {'mu_core':>10} {'ema_S':>9} {'S':>9} {'mu_eff':>9} {'E':>8} {'N':>8}")
    # 每 30 tick 打印一次 + 首尾
    printed = set()
    for r in trail:
        t = r['tick']
        if t in (1, 2, 3) or t % 30 == 0 or t == len(trail):
            if t not in printed:
                printed.add(t)
                print(f"{t:5d} {r['mu_core']:10.6f} {r['ema_S']:9.5f} {r['S']:9.5f} "
                      f"{r['mu_eff']:9.5f} {r['E']:8.4f} {r['N']:8.4f}")

    final = trail[-1]
    print(f"\n── 结果 ──")
    print(f"mu_core 起点:  0.500000")
    print(f"mu_core 终点:  {final['mu_core']:.6f}")
    print(f"mu_core 偏移:  {final['mu_core'] - 0.5:+.6f}")
    print(f"ema_S 终点:    {final['ema_S']:.6f}")
    print(f"S 终点:        {final['S']:.6f}")

    # 检查不可逆性：mu_core 显著偏离起点
    drift_final = final['mu_core'] - 0.5
    if abs(drift_final) > 0.005:   # >0.5% 漂移即为有效
        print(f"\n[结论] mu_core 被历史驱动，偏移 {drift_final:+.4f}，远离起点 0.5。偏移不可逆。")
    else:
        print(f"\n[问题] 漂移量过小 ({drift_final:+.6f})，需检查 S 驱动或 epsilon 设置。")


if __name__ == '__main__':
    main()
