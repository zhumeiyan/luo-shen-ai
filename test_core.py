#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_core.py — 认知核心三验证

三个测试：
1. 状态随时间演化（frames 不恒定）
2. 不同状态产出不同意图（intent 差异显著）
3. 相变检测触发（inject→tick→phase增加）

用法：python test_core.py
"""

import sys
import numpy as np

from cognitive_core import get_core, CognitiveCore, FRAME_DEPTH, GRID_ROWS, GRID_COLS


def test_1_state_evolution():
    """验证 1：状态随时间演化。跑 10 个 tick，确认帧持续变化。"""
    print("=" * 60)
    print("测试 1：状态随时间演化")
    print("=" * 60)
    
    core = get_core(seed=123)
    
    # 记录每帧的摘要
    snapshots = []
    for i in range(10):
        record = core.tick_step()
        frame_mean = float(np.mean(core.frames[-1]))
        snapshots.append(frame_mean)
        print(f"  tick={i+1}  frame_mean={frame_mean:+.6f}  phase={record['phase']}  error={record['error']:.6f}")
    
    # 验证：相邻帧之间有差异（不是恒定零）
    diffs = [abs(snapshots[i] - snapshots[i+1]) for i in range(len(snapshots)-1)]
    max_diff = max(diffs)
    mean_diff = sum(diffs) / len(diffs) if diffs else 0
    
    # 验证帧不是完全相同
    frames_any_different = False
    for i in range(1, FRAME_DEPTH):
        if not np.allclose(core.frames[0], core.frames[i]):
            frames_any_different = True
            break
    
    passed = max_diff > 1e-8 and frames_any_different
    
    print()
    print(f"  结论：最大相邻帧均值差 = {max_diff:.8f}")
    print(f"  结论：缓冲区中存在不同帧 = {frames_any_different}")
    print(f"  >>> 测试 1 {'通过' if passed else 'FAILED'}")
    return passed


def test_2_different_intents():
    """验证 2：不同状态产出不同意图。
    
    用两个不同的种子创建两个核心，跑相同 tick 数，
    比较它们的意图签名应该不同。
    """
    print()
    print("=" * 60)
    print("测试 2：不同状态产出不同意图")
    print("=" * 60)
    
    core_a = CognitiveCore(seed=100)
    core_b = CognitiveCore(seed=999)
    
    for _ in range(10):
        core_a.tick_step()
        core_b.tick_step()
    
    # 注入不同信号
    core_a.receive_input(signal={"energy": 0.8, "pain": 0.1})
    core_b.receive_input(signal={"energy": -0.5, "pain": 0.9})
    
    for _ in range(5):
        core_a.tick_step()
        core_b.tick_step()
    
    intent_a = core_a.read_intent()
    intent_b = core_b.read_intent()
    
    print(f"  A 意图签名: {intent_a['row_signature']}")
    print(f"  B 意图签名: {intent_b['row_signature']}")
    print(f"  A 能量: {intent_a['energy']:.4f}, 方向: {intent_a['direction']:+.4f}")
    print(f"  B 能量: {intent_b['energy']:.4f}, 方向: {intent_b['direction']:+.4f}")
    
    # 比较 row_signature 差异
    sig_a = np.array(intent_a['row_signature'])
    sig_b = np.array(intent_b['row_signature'])
    signature_diff = float(np.mean(np.abs(sig_a - sig_b)))
    
    # 活跃格不同
    cells_a = set(c['cell'] for c in intent_a['top_cells'][:3])
    cells_b = set(c['cell'] for c in intent_b['top_cells'][:3])
    cells_different = cells_a != cells_b
    
    print(f"  行签名平均差: {signature_diff:.4f}")
    print(f"  Top-3 活跃格是否不同: {cells_different}")
    print(f"    A top-3: {cells_a}")
    print(f"    B top-3: {cells_b}")
    
    passed = signature_diff > 0.001 or cells_different
    
    print(f"  >>> 测试 2 {'通过' if passed else 'FAILED'}")
    return passed


def test_3_phase_transition():
    """验证 3：相变检测触发。
    
    注入大幅脉冲使 prediction_error 超出阈值，
    相变被触发后 phase 应该增加。
    """
    print()
    print("=" * 60)
    print("测试 3：相变检测触发")
    print("=" * 60)
    
    core = get_core(seed=777)
    
    # 先跑一些 tick 让预测稳定
    for _ in range(10):
        core.tick_step()
    
    phase_before = core.phase
    print(f"  tick=10 时 phase = {phase_before}")
    
    # 注入 12 次大幅脉冲（每次大幅改变所有格子）
    # 这会导致 prediction_error 累积超标 → 相变
    pulse_count = 0
    for i in range(15):
        # 大脉冲：直接修改帧
        pulse = np.random.choice([-0.9, 0.9], size=(GRID_ROWS, GRID_COLS))
        core.frames[-1] = pulse
        record = core.tick_step()
        pulse_count += 1
        if core.phase > phase_before:
            print(f"  注入 {pulse_count} 次后相变触发！")
            print(f"  tick={record['tick']}  phase_before={phase_before}  phase_after={core.phase}")
            print(f"  相变历史（最近 3 条）：")
            for ph in core.phase_history[-3:]:
                print(f"    → phase {ph['from_phase']}→{ph['to_phase']}, errors_tail={ph['error_history_tail']}")
            break
        if i >= 14:
            print(f"  15 次注入后仍未相变。phase={core.phase}")
    
    phase_after = core.phase
    phase_changed = phase_after > phase_before
    
    # 也统计误差历史
    error_history = core._prediction_errors
    if error_history:
        print(f"  最近 5 个误差: {[round(e, 4) for e in error_history[-5:]]}")
    print(f"  阈值: {core._phase_error_threshold}, 连续次数上限: {core._phase_error_limit}")
    
    print(f"  >>> 测试 3 {'通过' if phase_changed else 'FAILED'}")
    return phase_changed


def main():
    print("认知核心测试套件 — 三验证")
    print(f"框架参数：T={FRAME_DEPTH} 网格={GRID_ROWS}×{GRID_COLS}")
    print()
    
    passed = []
    
    try:
        r1 = test_1_state_evolution()
        passed.append(("状态演化", r1))
    except Exception as e:
        print(f"  >>> 测试 1 异常: {e}")
        passed.append(("状态演化", False))
    
    try:
        r2 = test_2_different_intents()
        passed.append(("意图差异", r2))
    except Exception as e:
        print(f"  >>> 测试 2 异常: {e}")
        passed.append(("意图差异", False))
    
    try:
        r3 = test_3_phase_transition()
        passed.append(("相变触发", r3))
    except Exception as e:
        print(f"  >>> 测试 3 异常: {e}")
        passed.append(("相变触发", False))
    
    print()
    print("=" * 60)
    print("测试汇总")
    print("=" * 60)
    all_passed = True
    for name, result in passed:
        status = "通过" if result else "FAILED"
        print(f"  [{status}] {name}")
        if not result:
            all_passed = False
    
    print()
    print(f">>> 总结果: {'全部通过' if all_passed else '有测试失败'}")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
