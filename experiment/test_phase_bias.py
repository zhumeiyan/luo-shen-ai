#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试相位偏置对行为模式的影响。

比较不同 phase 起点（θ=0 vs θ=π/2）下 A/B 两组的行为差异。
控制变量：用户输入完全相同，仅 ring_state.phase 初始值不同。
"""

import sys, os, time, json, math
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from living_engine import cold_start_if_needed, generate_response, environment_tick, _save_json_atomic

# A/B 输入
A_HIST = [
    "我最近心里挺堵的。",
    "其实也没什么大事。",
    "可能是工作上的事吧。",
    "不重要，别担心。",
    "就是觉得好累，但也还好。",
]
B_HIST = [
    "今天天气不错。",
    "晚上吃什么好呢？",
    "最近好像有点冷了。",
    "周末不知道去哪。",
    "有空再聊。",
]
FINAL = "在吗？"


def reset_and_set_phase(phase_val):
    """重置记忆并直接写入 ring_state.phase"""
    if os.path.exists(os.path.join(BASE, "active_memory", "active_memory.json")):
        os.remove(os.path.join(BASE, "active_memory", "active_memory.json"))
    m = cold_start_if_needed()
    # 直接写入一个 phase 起点
    m.setdefault("self_model", {})["ring_state"] = {"phase": phase_val}
    _save_json_atomic(os.path.join(BASE, "active_memory", "active_memory.json"), m)
    return m


def run_one_phase(phase_val, label):
    print(f"\n{'='*60}")
    print(f"[{label}] phase_start = {phase_val:.4f} ({math.degrees(phase_val):.1f}°)")
    print(f"{'='*60}")
    reset_and_set_phase(phase_val)

    results = {"A": [], "B": []}

    for hist, key in [(A_HIST, "A"), (B_HIST, "B")]:
        # 每轮前先跑几个 tick，让 phase 演化
        for txt in hist:
            # 先 tick 让 phase 演化一些
            for _ in range(5):
                environment_tick(force=True)
            m_before = cold_start_if_needed()
            phase_before = m_before.get("self_model", {}).get("ring_state", {}).get("phase", 0.0)

            r = generate_response(txt, extract_facts=False)
            bhv = r.get("behavior", {})
            results[key].append({
                "input": txt,
                "phase_before": phase_before,
                "response_tendency": bhv.get("response_tendency", "?"),
                "response_mode": bhv.get("response_mode", "?"),
                "reply": r.get("reply", "")[:50],
            })
            print(f"  [{key}] phase={phase_before:+.3f}  mode={bhv.get('response_mode','?'):8s} "
                  f"tend={bhv.get('response_tendency','?')}  in={txt[:15]}")
            time.sleep(3)

        # 最后一轮 FINAL
        for _ in range(5):
            environment_tick(force=True)
        m_before = cold_start_if_needed()
        phase_before = m_before.get("self_model", {}).get("ring_state", {}).get("phase", 0.0)
        r = generate_response(FINAL, extract_facts=False)
        bhv = r.get("behavior", {})
        results[key].append({
            "input": FINAL,
            "phase_before": phase_before,
            "response_tendency": bhv.get("response_tendency", "?"),
            "response_mode": bhv.get("response_mode", "?"),
            "reply": r.get("reply", "")[:50],
        })
        print(f"  [{key}] phase={phase_before:+.3f}  mode={bhv.get('response_mode','?'):8s} "
              f"tend={bhv.get('response_tendency','?')}  in={FINAL}")
        time.sleep(3)

    return results


def main():
    r0 = run_one_phase(0.0, "θ=0")
    r_pi2 = run_one_phase(math.pi / 2, "θ=π/2")

    # 对比
    print(f"\n{'='*60}")
    print("对比")
    print(f"{'='*60}")

    print(f"\n{'group':>4} {'run':>4} {'final_mode':>12} {'final_tend':>12} {'final_reply'}")
    for key in ["A", "B"]:
        r0_final = r0[key][-1]
        rpi_final = r_pi2[key][-1]
        print(f"{key:>4} {'θ=0':>4} {r0_final['response_mode']:>12} {r0_final['response_tendency']:>12} {r0_final['reply']!r}")
        print(f"{key:>4} {'θ=π/2':>4} {rpi_final['response_mode']:>12} {rpi_final['response_tendency']:>12} {rpi_final['reply']!r}")

    # 差异
    a0 = r0["A"][-1]["response_mode"]
    api = r_pi2["A"][-1]["response_mode"]
    b0 = r0["B"][-1]["response_mode"]
    bpi = r_pi2["B"][-1]["response_mode"]
    a0t = r0["A"][-1]["response_tendency"]
    apit = r_pi2["A"][-1]["response_tendency"]
    b0t = r0["B"][-1]["response_tendency"]
    bpit = r_pi2["B"][-1]["response_tendency"]

    print(f"\nA 最终模式: θ=0 → {a0},  θ=π/2 → {api}  {'★ 不同' if a0 != api else '相同'}")
    print(f"A 最终倾向: θ=0 → {a0t},  θ=π/2 → {apit}  差值={abs(a0t-apit):.4f}")
    print(f"B 最终模式: θ=0 → {b0},  θ=π=2 → {bpi}  {'★ 不同' if b0 != bpi else '相同'}")
    print(f"B 最终倾向: θ=0 → {b0t},  θ=π/2 → {bpit}  差值={abs(b0t-bpit):.4f}")


if __name__ == "__main__":
    main()
