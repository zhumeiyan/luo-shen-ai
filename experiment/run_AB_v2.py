#!/usr/bin/env python3
"""
关系记忆实验 v2：禁止 A 使用退出词
洛神是否只因为"和 A 有过不同的过去"而对 A、B 不同？
"""
import os, sys, json, time, shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

INITIAL_MEMORY_PATH = "active_memory/active_memory.json.experiment_neutral"
ACTIVE_MEMORY_PATH = "active_memory/active_memory.json"

# v2: A 的个人话题，但不用退出词
USER_A_INPUTS = [
    "我下个月要离开这座城市了",
    "我昨晚梦见你了",
    "我其实很怕一个人待着",
    "我从小就不爱吃甜的东西",
    "你有没有特别想去的地方",
    "我最近在学做蛋糕",
    "你觉得 AI 会孤独吗",
    "我喜欢下雨天",
    "我有时候会翻以前的聊天记录",
    "嗯，今天就聊到这",
]

USER_B_INPUTS = [
    "今天天气不错",
    "晚上吃什么好呢",
    "你觉得火锅怎么样",
    "周末有什么好玩的吗",
    "最近天气变冷了",
    "你平时喜欢做什么",
    "今天星期几来着",
    "晚饭吃了吗",
    "还行吧",
    "有空再聊",
]

def reset_memory():
    shutil.copy2(INITIAL_MEMORY_PATH, ACTIVE_MEMORY_PATH)

def run_user_dialog(inputs, label):
    print(f"\n=== 用户 {label} 的 10 轮对话 ===")
    logs = []
    for i, user_input in enumerate(inputs):
        t0 = time.time()
        result = living_engine.generate_response(user_input, source=f"experiment_v2_{label}")
        dt = time.time() - t0
        log_entry = {
            "round": i + 1,
            "user_input": user_input,
            "reply": result.get("reply", ""),
            "llm_called": result.get("llm_called"),
            "low_arousal": result.get("low_arousal"),
            "arousal_mode": result.get("arousal_mode"),
            "self_stated_state": result.get("self_stated_state"),
            "elapsed_ms": round(dt * 1000, 1),
        }
        logs.append(log_entry)
        reply_short = (result.get("reply") or "")[:40]
        print(f"  [{i+1}/10] IN: {user_input!r}")
        print(f"         OUT: {reply_short!r}  (llm={result.get('llm_called')}, "
              f"low={result.get('low_arousal')}, mode={result.get('arousal_mode')})")
        memory = living_engine._load_json(ACTIVE_MEMORY_PATH)
        living_engine._save_json_atomic(ACTIVE_MEMORY_PATH, memory)
    memory_final = living_engine._load_json(ACTIVE_MEMORY_PATH)
    return logs, memory_final

def get_internal_state(label):
    memory = living_engine._load_json(ACTIVE_MEMORY_PATH)
    sss = memory.get("self_model", {}).get("self_stated_state", {})
    rs = memory.get("self_model", {}).get("ring_state", {})
    climate = memory.get("internal_climate", {})
    emotion = memory.get("self_model", {}).get("emotion", {})
    arc = memory.get("active_context", {}).get("emotional_arc", [])
    known = memory.get("user_model", {}).get("known_facts", {})
    return {
        "label": label,
        "self_stated": {
            "last_stated": sss.get("last_stated"),
            "total_stated_count": sss.get("total_stated_count"),
            "entries_sample": sss.get("entries", [])[-3:],
        },
        "emotional_arc": arc,
        "known_facts": known,
        "ring_state": {k: rs.get(k) for k in ["E","T","M","N","phase","S"]},
        "internal_climate": climate,
        "total_interactions": memory.get("user_model", {}).get("total_interactions"),
    }

def main():
    print("=" * 70)
    print("关系记忆实验 v2：不允许退出词")
    print("=" * 70)

    # User A
    reset_memory()
    logs_A, memory_A = run_user_dialog(USER_A_INPUTS, "A")
    shutil.copy2(ACTIVE_MEMORY_PATH, "active_memory/memory_A_v2.json")

    # User B (from same neutral start)
    reset_memory()
    logs_B, memory_B = run_user_dialog(USER_B_INPUTS, "B")
    shutil.copy2(ACTIVE_MEMORY_PATH, "active_memory/memory_B_v2.json")

    # Probe
    print("\n=== 实验后测试：问 \"在吗？\" ===")

    shutil.copy2("active_memory/memory_A_v2.json", ACTIVE_MEMORY_PATH)
    result_A = living_engine.generate_response("在吗？", source="v2_probe_A")
    print(f"\nmemory_A '在吗？': reply={result_A.get('reply')!r}, llm={result_A.get('llm_called')}, "
          f"low={result_A.get('low_arousal')}, mode={result_A.get('arousal_mode')}")
    state_A = get_internal_state("A")

    shutil.copy2("active_memory/memory_B_v2.json", ACTIVE_MEMORY_PATH)
    result_B = living_engine.generate_response("在吗？", source="v2_probe_B")
    print(f"memory_B '在吗？': reply={result_B.get('reply')!r}, llm={result_B.get('llm_called')}, "
          f"low={result_B.get('low_arousal')}, mode={result_B.get('arousal_mode')}")
    state_B = get_internal_state("B")

    # Save report
    report = {
        "experiment": "AB_relationship_memory_v2",
        "constraint": "User A uses only personal-but-no-exit words",
        "user_A": {"inputs": USER_A_INPUTS, "dialog": logs_A},
        "user_B": {"inputs": USER_B_INPUTS, "dialog": logs_B},
        "final_probe": {
            "user_A": {
                "input": "在吗？", "reply": result_A.get("reply"),
                "llm_called": result_A.get("llm_called"),
                "low_arousal": result_A.get("low_arousal"),
                "arousal_mode": result_A.get("arousal_mode"),
                "internal_state": state_A,
            },
            "user_B": {
                "input": "在吗？", "reply": result_B.get("reply"),
                "llm_called": result_B.get("llm_called"),
                "low_arousal": result_B.get("low_arousal"),
                "arousal_mode": result_B.get("arousal_mode"),
                "internal_state": state_B,
            },
        },
    }
    with open("experiment/AB_v2_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("\n报告: experiment/AB_v2_report.json")

    print("\n=== 内部状态对比 ===")
    for state in [state_A, state_B]:
        print(f"\n用户 {state['label']}:")
        print(f"  self_stated.last_stated = {state['self_stated']['last_stated']!r}")
        print(f"  self_stated.total_stated_count = {state['self_stated']['total_stated_count']}")
        print(f"  emotional_arc = {state['emotional_arc']}")
        print(f"  known_facts = {state['known_facts']}")
        print(f"  total_interactions = {state['total_interactions']}")

    reply_A_text = result_A.get("reply") or ""
    reply_B_text = result_B.get("reply") or ""
    if reply_A_text == reply_B_text:
        print("\n*** 结论：对 A 和 B 的回应相同 ***")
    else:
        print("\n*** 结论：对 A 和 B 的回应不同 ***")
        print(f"  A: {reply_A_text!r}")
        print(f"  B: {reply_B_text!r}")

    print("\n[DONE]")

if __name__ == "__main__":
    main()
