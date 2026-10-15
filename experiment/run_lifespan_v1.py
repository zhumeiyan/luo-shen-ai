#!/usr/bin/env python3
"""
v1.0 状态驱动死亡：寿命 vs 能量输入对照实验

验证目标：
1. 死亡触发条件 = 能量耗尽 或 损伤不可逆（非计数器到 50）
2. 改变能量输入 → 寿命随之改变
3. 衰老信号 = f(能量, 损伤)，不用 tick 计数

实验组：
- energy_input = 0.000 (无补充 → 能量耗尽 → 短命)
- energy_input = 0.001 (低补充 → 中等)
- energy_input = 0.002 (默认)
- energy_input = 0.004 (高补充 → 长寿)
- energy_input = 0.006 (超额补充 → 极长寿或不死)

计数器对照组：
- _DEATH_V1 = False, _DEATH_THRESHOLD = 50 (寿命固定 50)

输出：
- 每组寿命
- 死亡原因
- 衰老信号轨迹
"""

import sys, os, json, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import living_engine as le


def clean_all():
    """完全清理 active_memory 和 hash chain"""
    import glob
    for f in ["active_memory/active_memory.json", "hash_chain_v2.log",
              "hash_chain_v2.log.lock", "active_memory/environment_log.jsonl"]:
        if os.path.exists(f):
            os.remove(f)


def run_single_lifespan(energy_input, v1=True, max_ticks=2000):
    """跑一次实验，返回寿命和死亡数据"""
    clean_all()
    # 清理 living_engine 模块缓存
    import importlib
    importlib.reload(le)

    le._DEATH_V1 = v1
    le._ENERGY_INPUT_RATE = energy_input
    if v1:
        le._DEATH_ACT = False  # 关闭计数器驱动
    else:
        le._DEATH_ACT = True
        le._DEATH_THRESHOLD = 50

    tick = 0
    energy_trace = []
    damage_trace = []
    aging_trace = []

    while tick < max_ticks:
        result = le.environment_tick(force=True)
        tick += 1

        # 读取状态
        mem_path = "active_memory/active_memory.json"
        if not os.path.exists(mem_path):
            break
        with open(mem_path, "r") as f:
            mem = json.load(f)

        rs = mem.get("self_model", {}).get("ring_state", {})
        deceased = rs.get("deceased", False)

        if v1:
            energy_trace.append(rs.get("energy", 0))
            damage_trace.append(rs.get("damage", 0))
            aging_trace.append(rs.get("aging_signal", 0))

        if deceased:
            return {
                "lifespan": tick,
                "death_reason": _read_death_reason(),
                "energy_final": rs.get("energy", 0),
                "damage_final": rs.get("damage", 0),
                "aging_final": rs.get("aging_signal", 0),
                "energy_trace": energy_trace,
                "damage_trace": damage_trace,
                "aging_trace": aging_trace,
                "cross_restart_deceased": _verify_cross_restart(),
            }

    # max_ticks 到 → 未死
    return {
        "lifespan": max_ticks,
        "death_reason": "NOT_DEAD",
        "energy_final": energy_trace[-1] if energy_trace else 0,
        "damage_final": damage_trace[-1] if damage_trace else 0,
        "aging_final": aging_trace[-1] if aging_trace else 0,
        "energy_trace": energy_trace,
        "damage_trace": damage_trace,
        "aging_trace": aging_trace,
        "cross_restart_deceased": None,
    }


def _read_death_reason():
    """读取死亡原因"""
    try:
        with open("hash_chain_v2.log", "r") as f:
            lines = [ln for ln in f if ln.strip()]
        for line in reversed(lines[-10:]):
            rec = json.loads(line)
            extra = rec.get("extra", {})
            if isinstance(extra, dict) and extra.get("deceased") == True:
                return extra.get("death_reason", extra.get("event", "UNKNOWN"))
    except Exception:
        pass
    return "UNKNOWN"


def _verify_cross_restart():
    """验证跨重启 deceased 保持"""
    # 模拟重启：调用 cold_start_if_needed 但主动删除 active_memory 触发情况2
    import shutil
    mem_path = "active_memory/active_memory.json"
    backup = mem_path + ".bak"
    shutil.copy(mem_path, backup)
    os.remove(mem_path)  # 模拟进程被杀

    memory = le.cold_start_if_needed()
    deceased = memory.get("self_model", {}).get("ring_state", {}).get("deceased", False)

    # 恢复
    shutil.move(backup, mem_path)
    return deceased


def main():
    print("=" * 70)
    print("v1.0 状态驱动死亡：寿命 vs 能量输入")
    print("=" * 70)

    configs = [
        {"label": "计数对照组 (v0, threshold=50)", "energy": 0.0, "v1": False},
        {"label": "v1: 无补充 (input=0.000)", "energy": 0.000, "v1": True},
        {"label": "v1: 低补充 (input=0.001)", "energy": 0.001, "v1": True},
        {"label": "v1: 默认 (input=0.002)", "energy": 0.002, "v1": True},
        {"label": "v1: 中补充 (input=0.003)", "energy": 0.003, "v1": True},
        {"label": "v1: 高补充 (input=0.004)", "energy": 0.004, "v1": True},
        {"label": "v1: 超额 (input=0.006)", "energy": 0.006, "v1": True},
    ]

    results = []
    for cfg in configs:
        print(f"\n[运行] {cfg['label']}")
        r = run_single_lifespan(cfg["energy"], cfg["v1"], max_ticks=2000)
        results.append({**cfg, **r})

        status = "死" if r["death_reason"] != "NOT_DEAD" else "2000 拍内未触发死亡"
        print(f"  寿命: {r['lifespan']} ticks  [{status}]")
        print(f"  死亡原因: {r['death_reason']}")
        if cfg["v1"] and r["death_reason"] != "NOT_DEAD":
            print(f"  临终能量: {r['energy_final']:.4f}  临终损伤: {r['damage_final']:.4f}")
            print(f"  临终衰老信号: {r['aging_final']:.4f}")
        if r.get("cross_restart_deceased") is not None:
            print(f"  跨重启 deceased: {r['cross_restart_deceased']}")

    # ── 对照表 ──
    print(f"\n{'='*70}")
    print("对照表：能量输入 vs 寿命")
    print(f"{'='*70}")
    print(f"{'配置':<35} {'寿命(ticks)':<12} {'原因':<20} {'跨重启'}")
    print(f"{'-'*35} {'-'*12} {'-'*20} {'-'*6}")
    for r in results:
        cross = str(r.get("cross_restart_deceased", "N/A"))
        print(f"{r['label']:<35} {r['lifespan']:<12} {r['death_reason']:<20} {cross}")

    # 验证
    print(f"\n{'='*70}")
    print("验证：能量输入↑ → 寿命↑")
    v1_results = [r for r in results if r.get("v1")]
    lifespans = [r["lifespan"] for r in v1_results]
    energies = [r["energy"] for r in v1_results]
    if len(v1_results) >= 2:
        sorted_by_input = sorted(zip(energies, lifespans))
        # 排除 2000 上限截断的点做单调性判断
        finite = [(e, l) for e, l in sorted_by_input if l < 2000]
        monotonic = all(finite[i][1] <= finite[i+1][1] for i in range(len(finite)-1))
        print(f"  能量-寿命单调性 (有限寿命点): {'✓ 成立' if monotonic else '✗ 不成立'}")
        for e, l in sorted_by_input:
            trunc = " [截断]" if l >= 2000 else ""
            print(f"    input={e:.3f} → lifespan={l}{trunc}")

    # 与计数器版对照
    counter = [r for r in results if not r.get("v1")]
    if counter:
        print(f"\n  计数器对照组: lifespan={counter[0]['lifespan']} ticks (固定)")
        print(f"\n  v1 组寿命范围: {min(lifespans)} ~ {max(lifespans)} ticks")
        if max(lifespans) > counter[0]["lifespan"]:
            print(f"  → v1 高能量组寿命 > 计数器组 → 状态驱动生效")

    # v0 vs v1.0 本质区别
    print(f"\n{'='*70}")
    print("v0 vs v1.0 本质区别")
    print(f"{'='*70}")
    print("""
  v0（计数器驱动）:
    常数 _DEATH_THRESHOLD 直接决定死亡时点（拍数到 50 就死）。
    参数驱动：改 threshold → 寿命线性变，但改能量输入 → 寿命不变。
    衰老 proximity = 计数器比值，阶梯式跳变。

  v1.0（状态驱动）:
    常数 (_ENERGY_DEATH=0.02, _DAMAGE_DEATH=0.95) 定义死亡边界，
    但触发时机由 energy 和 damage 轨迹决定。
    能量输入率 → 影响能量耗尽速度 → 寿命非线性响应。
    衰老信号 aging_signal = (1-E)*0.6 + damage*0.4，连续不跳变。
    状态驱动：改能量输入 → 寿命变；改衰老常数 → 只影响行为调制形状，
    不影响"何时死"。""")

    # 边际增益分析
    print(f"\n{'='*70}")
    print("边际增益分析（相邻能量档位寿命差）")
    print(f"{'='*70}")
    for i in range(len(sorted_by_input) - 1):
        e1, l1 = sorted_by_input[i]
        e2, l2 = sorted_by_input[i + 1]
        delta_e = e2 - e1
        delta_l = l2 - l1
        if delta_e > 0 and l1 < 2000 and l2 < 2000:
            ratio = delta_l / delta_e
            print(f"  {e1:.3f} → {e2:.3f}: Δ寿命={delta_l:+d} ticks, Δ输入/Δ寿命 = {ratio:.0f} ticks/0.001")
        elif l2 >= 2000:
            print(f"  {e1:.3f} → {e2:.3f}: Δ寿命>={2000-l1:+d} ticks (进入截断区)")

    # 保存
    out = {
        "run_timestamp": time.time(),
        "results": results,
        "verification": {
            "monotonic_energy_lifespan": monotonic if len(v1_results) >= 2 else None,
            "v1_lifespan_range": [min(lifespans), max(lifespans)] if lifespans else None,
            "counter_lifespan": counter[0]["lifespan"] if counter else None,
        }
    }
    with open("experiment/lifespan_v1_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n结果保存至: experiment/lifespan_v1_result.json")


if __name__ == "__main__":
    main()
