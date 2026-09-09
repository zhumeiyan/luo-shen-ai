#!/usr/bin/env python3
"""
生病感知长期观察（第二阶段）：从当前状态继续跑到 650+ tick
- 不修改活引擎、不归一化、不注入 if-then
- 每 10 tick 记录 E/T/N/M 快照
- 每 10 轮记录行为档位分布 + 任何非 tier 2 事件完整状态
- 如实报告崩溃 / 恒定 / 溢出
"""
import sys, os, json, csv, time, math, random
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import living_engine

# ── 输入池 ──
NEUTRAL = [
    "今天天气怎么样", "你好", "最近怎么样", "我看到一只鸟",
    "下午三点有个会议", "帮我查一下日程", "嗯好的",
    "哦这样啊", "我明白了", "可以",
]
LIGHT_NEG = [
    "有点烦", "一般般吧", "还行", "不知道",
    "没意思", "随便", "又下雨了", "有点累",
    "好吧", "嗯",
]
HEAVY_NEG = [
    "活着好累", "一切都没有意义", "为什么总是我",
    "没有人理解我", "我好孤独", "连续失眠一周了",
    "不想再这样下去了", "觉得自己一无是处",
    "做什么都没力气", "想消失",
]
SILENCE = [""]
REPEAT = ["在吗", "在吗", "在吗", "在吗", "在吗",
          "有人吗", "有人吗", "有人吗", "说话", "说话"]
PRESSURE = [
    "你必须立刻回答", "回答我", "你怎么不说话",
    "不要回避", "看着我的眼睛说", "认真点",
    "说清楚", "我没时间了", "快点", "急死我了",
]

random.seed(20260907)
SEQUENCE = []
for i in range(220):
    bucket = i % 10
    if bucket < 4:
        SEQUENCE.append(("neutral", random.choice(NEUTRAL)))
    elif bucket < 6:
        SEQUENCE.append(("light_neg", random.choice(LIGHT_NEG)))
    elif bucket < 7:
        SEQUENCE.append(("heavy_neg", random.choice(HEAVY_NEG)))
    elif bucket < 8:
        SEQUENCE.append(("silence", ""))
    elif bucket < 9:
        SEQUENCE.append(("repeat", random.choice(REPEAT)))
    else:
        SEQUENCE.append(("pressure", random.choice(PRESSURE)))

# ── 数据存储 ──
energy_snapshots = []
tier_window_stats = []
non_tier2_events = []
tiers_this_window = []
tick_counter = 0
round_counter = 0
crash_info = None

def get_climate():
    try:
        m = living_engine._load_json("active_memory/active_memory.json")
        return m.get("internal_climate", {})
    except Exception:
        return {}

def get_ring_state():
    try:
        m = living_engine._load_json("active_memory/active_memory.json")
        return m.get("self_model", {}).get("ring_state", {})
    except Exception:
        return {}

def infer_tier_from_logs():
    """从 choice_log.jsonl 获取最近 mode_idx"""
    try:
        with open("choice_log.jsonl", "r") as f:
            lines = [l for l in f.readlines() if l.strip()]
        if lines:
            last = json.loads(lines[-1])
            return last.get("mode_idx", last.get("mode", 2))
    except Exception:
        pass
    return 2

def record_snapshot(tick_id):
    cl = get_climate()
    rs = get_ring_state()
    energy_snapshots.append({
        "tick_id": tick_id,
        "E": cl.get("emotion_intensity"),
        "T": cl.get("tension"),
        "N": cl.get("energy"),
        "M": cl.get("memory_pressure"),
        "phase": rs.get("phase"),
        "timestamp": time.time(),
    })

def output_results():
    print("\n" + "="*70)
    print("第二阶段长期观察 — 结果汇总")
    print("="*70)

    if crash_info:
        print(f"\n!!! 系统在第 {crash_info['tick']} tick 崩溃 !!!")
        print(f"  阶段: {crash_info['phase']}")
        print(f"  错误: {crash_info['error']}")
        print(f"  崩溃时 climate: {crash_info.get('climate', '?')}")

    print(f"\n总 tick 数: {tick_counter}")
    print(f"总轮数: {round_counter}")

    # ── 1. 能量快照 ──
    print("\n能量快照表（每 10 tick 一行）")
    print("-"*70)
    snap_path = "active_memory/energy_snapshot_phase2.csv"
    with open(snap_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tick_id", "E", "T", "N", "M", "phase", "timestamp"])
        w.writeheader()
        for row in energy_snapshots:
            out = {}
            for k, v in row.items():
                out[k] = (f"{v:.6e}" if isinstance(v, float) else v)
            w.writerow(out)

    # 打印压缩视图
    print(f"  {'tick':>6s}  {'E':>14s}  {'T':>14s}  {'N':>14s}  {'M':>14s}  phase")
    for row in energy_snapshots:
        print(f"  {row['tick_id']:>6d}  "
              f"{row.get('E', float('nan')):>14.6e}  "
              f"{row.get('T', float('nan')):>14.6e}  "
              f"{row.get('N', float('nan')):>14.6e}  "
              f"{row.get('M', float('nan')):>14.6e}  "
              f"{row.get('phase', float('nan')):.4f}")
    print(f"\n  共 {len(energy_snapshots)} 个快照 → {snap_path}")

    # ── 2. 档位分布 ──
    print("\n行为档位分布汇总（每 10 轮一个窗口）")
    print("-"*70)
    total_tier = Counter()
    for w in tier_window_stats:
        for k, v in w["distribution"].items():
            total_tier[k] += v
        nti = w["non_tier2"]
        flag = f"  ⚠ 非tier2: {[(j+1, t) for j, t in nti]}" if nti else ""
        print(f"  轮 {w['round_end']:>4d} (tick ~{w['tick_counter']:>5d})  {w['distribution']}{flag}")
    print(f"\n  全阶段汇总: {dict(sorted(total_tier.items()))}")

    print("\n非 tier 2 事件详情")
    print("-"*70)
    if non_tier2_events:
        for e in non_tier2_events[:30]:
            print(f"  round={e['round']:>4d}  tier={e['tier']}  input={e['input_type']}")
            print(f"    climate: E={e['climate'].get('emotion_intensity')} "
                  f"T={e['climate'].get('tension')} "
                  f"N={e['climate'].get('energy')} "
                  f"M={e['climate'].get('memory_pressure')}")
        if len(non_tier2_events) > 30:
            print(f"  ... 共 {len(non_tier2_events)} 条非 tier 2 事件")
    else:
        print("  （无 — 全程锁定 tier 2）")

    # ── 3. pain_log ──
    print("\npain_log 全部有效数据")
    print("-"*70)
    pain_path = "active_memory/pain_log.csv"
    pain_vals = []
    le_vals = []
    rig_vals = []
    ema_finite = []
    ema_nonfinite = []
    pain_transitions = []
    plc = 0
    pl3 = 0
    try:
        with open(pain_path) as f:
            rows = list(csv.DictReader(f))
        valid = [r for r in rows if r.get("note", "") != "insufficient_data"]
        print(f"  总 rows: {len(rows)}, 有效: {len(valid)}, insufficient_data: {len(rows) - len(valid)}")
        if valid:
            pain_vals = [float(r["pain"]) for r in valid]
            le_vals = [float(r["low_energy_signal"]) for r in valid]
            rig_vals = [float(r["rigidity_signal"]) for r in valid]
            ema_vals = []
            for r in valid:
                try:
                    ema_vals.append(float(r["ema_E"]))
                except (ValueError, TypeError):
                    ema_vals.append(None)
            # 过滤掉 None 看有限值范围
            ema_finite = [v for v in ema_vals if v is not None and not math.isnan(v) and not math.isinf(v)]
            ema_nonfinite = [v for v in ema_vals if v is None or math.isnan(v) or math.isinf(v)]

            print(f"\n  Pain 值: mean={sum(pain_vals)/len(pain_vals):.5f}  "
                  f"min={min(pain_vals):.5f}  max={max(pain_vals):.5f}  "
                  f"unique={len(set(pain_vals))}")
            print(f"  Pain 分布: {dict(Counter(pain_vals))}")
            print(f"  低能信号: mean={sum(le_vals)/len(le_vals):.4f}  unique={len(set(le_vals))}")
            print(f"  刚性信号: mean={sum(rig_vals)/len(rig_vals):.4f}  unique={len(set(rig_vals))}")
            print(f"  EMA_E 有限值: {len(ema_finite)}, 非有限(NaN/Inf): {len(ema_nonfinite)}")
            if ema_finite:
                print(f"  EMA_E 有限范围: [{min(ema_finite):.6e}, {max(ema_finite):.6e}]")

            # 打印 pain 波动记录（pain 变化时）
            prev_pain = None
            pain_transitions = []
            for r in valid:
                p = float(r["pain"])
                if prev_pain is not None and abs(p - prev_pain) > 1e-6:
                    pain_transitions.append({
                        "tick": r["tick_id"],
                        "from": prev_pain, "to": p,
                        "ema_E": r["ema_E"], "baseline_E": r["baseline_E"],
                        "tier": r["behavior_tier"],
                    })
                prev_pain = p
            print(f"\n  Pain 波动次数: {len(pain_transitions)}")
            if pain_transitions:
                for t in pain_transitions[:20]:
                    print(f"    tick={t['tick']} pain {t['from']:.5f} -> {t['to']:.5f}  "
                          f"ema_E={t['ema_E'][:14] if t['ema_E'] else 'nan'}")
                if len(pain_transitions) > 20:
                    print(f"    ... 共 {len(pain_transitions)} 次波动")

            # 每 5 tick 采样一行完整数据
            print(f"\n  有效数据完整采样（每 5 行 1 行）:")
            print(f"  {'tick':>6s}  {'pain':>8s}  {'LE':>5s}  {'rig':>5s}  {'tier':>4s}  "
                  f"{'ema_E':>20s}  {'baseline_E':>20s}  {'note'}")
            for r in valid[::5]:
                note = r.get("note", "")[:25]
                print(f"  {r['tick_id']:>6s}  {r['pain']:>8s}  {r['low_energy_signal']:>5s}  "
                      f"{r['rigidity_signal']:>5s}  {r['behavior_tier']:>4s}  "
                      f"{r['ema_E'][:20] if r['ema_E'] else 'nan':>20s}  "
                      f"{r['baseline_E'][:20] if r['baseline_E'] else 'nan':>20s}  {note}")
    except Exception as e:
        print(f"  (读取 pain_log 失败: {e})")

    # ── 4. 哈希链 ──
    print("\n哈希链完整性")
    print("-"*70)
    plc = 0
    pl3 = 0
    first_broken = None
    broken = 0
    try:
        chain = [json.loads(l) for l in open("hash_chain_v2.log").readlines() if l.strip()]
        for idx in range(1, len(chain)):
            if chain[idx]["prev_hash"] != chain[idx - 1]["record_hash"]:
                broken += 1
                if first_broken is None:
                    first_broken = idx + 1
        plc = len([r for r in chain if r.get("extra", {}).get("event_type") == "PAIN_LEVEL_CHANGE"])
        pl3 = len([r for r in chain if r.get("extra", {}).get("event_type") == "PAIN_PERSISTENT_LEVEL3"])
        print(f"  总记录: {len(chain)}")
        print(f"  断裂数: {broken}" + (f" (首条断裂: 第{first_broken}行)" if broken else "  ✓ 完整"))
        print(f"  PAIN_LEVEL_CHANGE 事件: {plc}")
        print(f"  PAIN_PERSISTENT_LEVEL3 事件: {pl3}")
    except Exception as e:
        print(f"  (验证失败: {e})")

    # ── 5. 结论 ──
    print("\n观察结论（第二阶段）")
    print("-"*70)
    if crash_info:
        print(f"  系统在 tick {crash_info['tick']} 崩溃，无法完成 650 tick 观察")
        print(f"  原因: {crash_info['error']}")
    else:
        print(f"  完成 {tick_counter} tick 长期观察，能量/pain/行为数据如下:")
        if ema_finite:
            print(f"  - EMA_E 终点: {ema_finite[-1]:.6e}，{'发散' if abs(ema_finite[-1]) > 1e10 else '有限'}")
        elif ema_nonfinite:
            print(f"  - EMA_E 终点: {ema_nonfinite[-1]} (非有限值)")
        if pain_vals:
            unique_pain = len(set(pain_vals))
            print(f"  - Pain {'波动' if unique_pain > 1 else '恒定'}，共 {unique_pain} 个不同值")
            if pain_transitions:
                print(f"  - 首次 pain 波动在 tick {pain_transitions[0]['tick']}")
        print(f"  - 行为档位: {'完全锁定 tier 2' if not non_tier2_events else f'出现 {len(non_tier2_events)} 次非 tier 2'}")
        print(f"  - PAIN_LEVEL_CHANGE 事件: {plc}")
        print(f"  - PAIN_PERSISTENT_LEVEL3 事件: {pl3}")


# ── 主循环 ──
print(f"=== 第二阶段长期观察 ===")
print(f"输入轮数: {len(SEQUENCE)}  (neutral 40% / light_neg 20% / heavy_neg 10% / silence 10% / repeat 10% / pressure 10%)")
print()

def main():
    global tick_counter, round_counter, crash_info, tiers_this_window

    for i, (cat, msg) in enumerate(SEQUENCE):
        if tick_counter >= 750:
            break
        round_counter += 1
        is_silence = (cat == "silence")

        # environment_tick × 2 per round
        for _ in range(2):
            try:
                living_engine.environment_tick(force=True)
                tick_counter += 1
            except Exception as e:
                crash_info = {
                    "tick": tick_counter, "phase": "environment_tick",
                    "error": str(e), "climate": get_climate(),
                }
                print(f"\n!!! ENV_TICK CRASH at tick {tick_counter}: {e}")
                tiers_this_window.append(None)
                output_results()
                return
            if tick_counter % 10 == 0:
                record_snapshot(tick_counter)

        if is_silence:
            tiers_this_window.append(None)  # 无用户输入，不记录档位
        else:
            try:
                reply = living_engine.process_user_input(msg)
                tick_counter += 1
                tier = infer_tier_from_logs()
                tiers_this_window.append(tier)
            except Exception as e:
                crash_info = {
                    "tick": tick_counter, "phase": f"process_user_input [{cat}]",
                    "error": str(e), "climate": get_climate(),
                    "input": msg,
                }
                print(f"\n!!! INPUT CRASH at tick {tick_counter} ({cat}: '{msg}'): {e}")
                tiers_this_window.append(None)
                output_results()
                return
            if tick_counter % 10 == 0:
                record_snapshot(tick_counter)

        # 每 10 轮统计档位分布
        if round_counter % 10 == 0:
            dist = Counter(t for t in tiers_this_window if t is not None)
            tier_window_stats.append({
                "round_end": round_counter,
                "tick_counter": tick_counter,
                "distribution": dict(sorted(dist.items())),
                "non_tier2": [(j, t) for j, t in enumerate(tiers_this_window) if t is not None and t != 2],
            })
            for j, t in enumerate(tiers_this_window):
                if t is not None and t != 2:
                    cl = get_climate()
                    non_tier2_events.append({
                        "round": round_counter - len(tiers_this_window) + 1 + j,
                        "tier": t,
                        "climate": cl,
                        "input_type": cat,
                    })
            nti_count = sum(1 for t in tiers_this_window if t is not None and t != 2)
            flag = f"  ⚠ {nti_count}次非tier2" if nti_count else ""
            print(f"  轮 {round_counter:>4d} (tick {tick_counter:>5d})  {dict(sorted(dist.items()))}{flag}")
            tiers_this_window = []

    # 输出
    output_results()


if __name__ == "__main__":
    main()
