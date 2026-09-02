#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A/B 不可逆性测试：同一起点 + 不同历史路径 → mu_core 收敛到不同终点。

机制：通过 __meta.L_override 给环境不同的"长期身体势"（模拟不同历史积累的高/低熵）。
- 序列 A（"高熵历史"）：L=0.8 强身体势驱动，环振幅大 → S 上升 → mu_core 被拉高
- 序列 B（"低熵历史"）：L=0.2 弱身体势驱动，环振幅小 → S 低 → mu_core 被拉低

步骤：
1. 冷启动 mu_core=0.5, ema_S=0, S=0
2. Series A: L=0.8 跑 800 tick → mu_core_final_A
3. 重置冷启动 mu_core=0.5, ema_S=0, S=0（确保起点相同）
4. Series B: L=0.2 跑 800 tick → mu_core_final_B
5. 比较 A vs B：mu_core_final 不同 → 历史永久改变了环的参数
"""
import sys, os, time
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from living_engine import (
    cold_start_if_needed, _save_json_atomic,
    environment_tick, _load_json,
)

def reset_cold():
    """彻底冷启动重置：mu_core=0.5, ema_S=0, S=0"""
    m = cold_start_if_needed()
    m['internal_climate'] = {
        'emotion_intensity': 0.5, 'tension': 0.0,
        'energy': 0.5, 'memory_pressure': 0.3,
    }
    if 'self_model' not in m:
        m['self_model'] = {}
    m['self_model']['ring_state'] = {'mu_core': 0.5, 'ema_S': 0.0, 'S': 0.0}
    if '__meta' not in m:
        m['__meta'] = {}
    m['__meta']['L_override'] = None  # 清除任何残留
    _save_json_atomic('active_memory/active_memory.json', m)


def run_series(l_override, n_ticks=400):
    """跑 n_ticks，每 tick 强制 L=l_override，返回 mu_core 轨迹 + 终态"""
    reset_cold()
    trail = []
    for i in range(n_ticks):
        m = cold_start_if_needed()
        m['__meta']['L_override'] = l_override   # 每次 tick 覆盖 L
        _save_json_atomic('active_memory/active_memory.json', m)
        environment_tick(force=True)

        m2 = _load_json('active_memory/active_memory.json')
        rs = m2.get('self_model', {}).get('ring_state', {})
        climate = m2.get('internal_climate', {})
        trail.append({
            'tick': i + 1,
            'mu_core': rs.get('mu_core', 0.5),
            'ema_S': rs.get('ema_S', 0.0),
            'S': rs.get('S', 0.0),
            'E': climate.get('emotion_intensity', 0),
            'N': climate.get('energy', 0),
            'M': climate.get('memory_pressure', 0),
        })
    return trail


def main():
    print("===== A/B 不可逆性测试 =====")
    print("同一起点 mu_core=0.5, ema_S=0, S=0")
    print("Series A: L=0.8 (高身体势)")
    print("Series B: L=0.2 (低身体势)\n")

    print("跑 Series A...")
    trail_a = run_series(0.8, 400)

    print("跑 Series B (重置冷启动，与 A 同一起点)...")
    trail_b = run_series(0.2, 400)

    # ── 打印 A 的轨迹 (每 100 tick) ──
    print(f"\n── Series A (L=0.8) mu_core 轨迹 ──")
    print(f"{'tick':>5} {'mu_core':>10} {'ema_S':>9} {'S':>9} {'E':>8} {'N':>8}")
    for r in trail_a:
        if r['tick'] in (1, 10, 50) or r['tick'] % 100 == 0 or r['tick'] == 400:
            print(f"{r['tick']:5d} {r['mu_core']:10.6f} {r['ema_S']:9.5f} {r['S']:9.5f} "
                  f"{r['E']:8.4f} {r['N']:8.4f}")

    # ── 打印 B 的轨迹 (每 100 tick) ──
    print(f"\n── Series B (L=0.2) mu_core 轨迹 ──")
    print(f"{'tick':>5} {'mu_core':>10} {'ema_S':>9} {'S':>9} {'E':>8} {'N':>8}")
    for r in trail_b:
        if r['tick'] in (1, 10, 50) or r['tick'] % 100 == 0 or r['tick'] == 400:
            print(f"{r['tick']:5d} {r['mu_core']:10.6f} {r['ema_S']:9.5f} {r['S']:9.5f} "
                  f"{r['E']:8.4f} {r['N']:8.4f}")

    # ── 比较终点 ──
    a_final = trail_a[-1]['mu_core']
    b_final = trail_b[-1]['mu_core']
    diff = a_final - b_final
    print(f"\n── 终点比较 ──")
    print(f"mu_core 起点 (A/B 共享): 0.500000")
    print(f"mu_core 终点 A (L=0.8):  {a_final:.6f} 偏移 {a_final - 0.5:+.6f}")
    print(f"mu_core 终点 B (L=0.2):  {b_final:.6f} 偏移 {b_final - 0.5:+.6f}")
    print(f"A vs B 终点差值: {diff:+.6f}")
    print(f"差异占初始值比例: {abs(diff) / 0.5 * 100:.2f}%")

    if abs(diff) > 0.001:
        print(f"\n[结论] 不同历史路径使 mu_core 收敛到不同终点 (Δ={diff:+.4f})。")
        print("       环的形状被历史记忆永久改变。")
    else:
        print(f"\n[问题] A/B 终点差异过小 ({diff:+.6f})，需要检查。")


if __name__ == '__main__':
    main()
