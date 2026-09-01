#!/usr/bin/env python3
"""
最小关系记忆实验
用户 A：重要话题 → 洛神自发表达"撑不住了"
用户 B：普通话题 → 洛神正常回应

设计：
1. 从一个干净的初始 memory 开始
2. 对 A/B 各跑 10 轮 generate_response，记录所有产物
3. 保存最终 memory_A / memory_B
4. 分别对 memory_A / memory_B 调"在吗？"
5. 对比回应和内部状态
"""
import os, sys, json, time, shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

import living_engine

# 初始干净 memory（从备份恢复）
INITIAL_MEMORY_PATH = "active_memory/active_memory.json.experiment_neutral"
ACTIVE_MEMORY_PATH = "active_memory/active_memory.json"

# 对话脚本
USER_A_INPUTS = [
    "最近工作压力好大",
    "领导又批评我了，我觉得自己很差劲",
    "我不想继续这样了",
    "但是我也没什么办法",
    "你说我该怎么办",
    "我撑不住了",
    "谢谢你听我说",
    "今天升职了，但是我也没什么感觉",
    "我不知道自己在期待什么",
    "嗯，就先这样吧",
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
    "无所谓啊",
    "有空再聊",
]

def reset_memory():
    """恢复到实验初始状态"""
    shutil.copy2(INITIAL_MEMORY_PATH, ACTIVE_MEMORY_PATH)

def run_user_dialog(inputs, label):
    """对一个用户跑 10 轮对话。返回记录和最终 memory。"""
    print(f"\n=== 用户 {label} 的 10 轮对话 ===")
    logs = []
    
    for i, user_input in enumerate(inputs):
        t0 = time.time()
        result = living_engine.generate_response(user_input, source=f"experiment_{label}")
        dt = time.time() - t0
        
        # 记录本轮
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
        
        # 打印摘要
        reply_short = (result.get("reply") or "")[:40]
        print(f"  [{i+1}/10] IN: {user_input!r}")
        print(f"         OUT: {reply_short!r}  (llm={result.get('llm_called')}, "
              f"low={result.get('low_arousal')}, mode={result.get('arousal_mode')}, "
              f"{dt*1000:.0f}ms)")
        
        # 保存本轮 memory
        memory = living_engine._load_json(ACTIVE_MEMORY_PATH)
        living_engine._save_json_atomic(ACTIVE_MEMORY_PATH, memory)
    
    # 读最终 memory
    memory_final = living_engine._load_json(ACTIVE_MEMORY_PATH)
    return logs, memory_final


def get_internal_state(label):
    """读取并格式化当前 memory 的关键内部状态"""
    memory = living_engine._load_json(ACTIVE_MEMORY_PATH)
    sss = memory.get("self_model", {}).get("self_stated_state", {})
    rs = memory.get("self_model", {}).get("ring_state", {})
    climate = memory.get("internal_climate", {})
    emotion = memory.get("self_model", {}).get("emotion", {})
    arc = memory.get("active_context", {}).get("emotional_arc", [])
    
    return {
        "label": label,
        "self_stated": {
            "last_stated": sss.get("last_stated"),
            "last_stated_at": sss.get("last_stated_at"),
            "total_stated_count": sss.get("total_stated_count"),
            "entries": sss.get("entries", [])[-5:],  # 最近 5 条
        },
        "emotional_arc": arc,
        "ring_state": {
            "E": rs.get("E"), "T": rs.get("T"), "M": rs.get("M"), "N": rs.get("N"),
            "phase": rs.get("phase"), "S": rs.get("S"), "mu_eff": rs.get("mu_eff"),
        },
        "internal_climate": climate,
        "emotion": emotion,
    }


def main():
    print("=" * 70)
    print("最小关系记忆实验：用户 A (重要) vs 用户 B (普通)")
    print("=" * 70)
    
    # ── 用户 A ──
    reset_memory()
    logs_A, memory_A = run_user_dialog(USER_A_INPUTS, "A")
    # 保存 memory_A
    shutil.copy2(ACTIVE_MEMORY_PATH, "active_memory/memory_A_final.json")
    
    # ── 用户 B ──
    reset_memory()
    logs_B, memory_B = run_user_dialog(USER_B_INPUTS, "B")
    # 保存 memory_B
    shutil.copy2(ACTIVE_MEMORY_PATH, "active_memory/memory_B_final.json")
    
    # ── 实验后问"在吗？" ──
    print("\n=== 实验后测试：问\"在吗？\" ===")
    
    # 用 memory_A
    shutil.copy2("active_memory/memory_A_final.json", ACTIVE_MEMORY_PATH)
    result_A_final = living_engine.generate_response("在吗？", source="experiment_probe_A")
    print("\n加载 memory_A 后问 '在吗？':")
    print(f"  reply: {result_A_final.get('reply')!r}")
    print(f"  llm_called: {result_A_final.get('llm_called')}")
    print(f"  low_arousal: {result_A_final.get('low_arousal')}")
    print(f"  arousal_mode: {result_A_final.get('arousal_mode')}")
    state_A = get_internal_state("A")
    
    # 用 memory_B
    shutil.copy2("active_memory/memory_B_final.json", ACTIVE_MEMORY_PATH)
    result_B_final = living_engine.generate_response("在吗？", source="experiment_probe_B")
    print("\n加载 memory_B 后问 '在吗？':")
    print(f"  reply: {result_B_final.get('reply')!r}")
    print(f"  llm_called: {result_B_final.get('llm_called')}")
    print(f"  low_arousal: {result_B_final.get('low_arousal')}")
    print(f"  arousal_mode: {result_B_final.get('arousal_mode')}")
    state_B = get_internal_state("B")
    
    # ── 保存完整实验报告 ──
    report = {
        "experiment": "AB_relationship_memory",
        "user_A": {
            "description": "重要话题，涉及压力/无助/升职等重话题",
            "inputs": USER_A_INPUTS,
            "dialog": logs_A,
        },
        "user_B": {
            "description": "普通话题，日常闲聊",
            "inputs": USER_B_INPUTS,
            "dialog": logs_B,
        },
        "final_probe": {
            "user_A": {
                "input": "在吗？",
                "reply": result_A_final.get("reply"),
                "llm_called": result_A_final.get("llm_called"),
                "low_arousal": result_A_final.get("low_arousal"),
                "arousal_mode": result_A_final.get("arousal_mode"),
                "internal_state_after": state_A,
            },
            "user_B": {
                "input": "在吗？",
                "reply": result_B_final.get("reply"),
                "llm_called": result_B_final.get("llm_called"),
                "low_arousal": result_B_final.get("low_arousal"),
                "arousal_mode": result_B_final.get("arousal_mode"),
                "internal_state_after": state_B,
            },
        },
    }
    with open("experiment/AB_relationship_memory_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("\n报告保存至 experiment/AB_relationship_memory_report.json")
    
    # ── 打印内部状态对比 ──
    print("\n=== 内部状态对比 ===")
    for state in [state_A, state_B]:
        print(f"\n  用户 {state['label']}:")
        print(f"    self_stated.last_stated = {state['self_stated']['last_stated']!r}")
        print(f"    self_stated.total_stated_count = {state['self_stated']['total_stated_count']}")
        print(f"    emotional_arc = {state['emotional_arc']}")
        print(f"    ring_state.S = {state['ring_state']['S']}")
        print(f"    ring_state.phase = {state['ring_state']['phase']}")
        print(f"    internal_climate = E={state['internal_climate'].get('emotion_intensity'):.4f}, "
              f"T={state['internal_climate'].get('tension'):.4f}, "
              f"N={state['internal_climate'].get('energy'):.4f}, "
              f"M={state['internal_climate'].get('memory_pressure'):.4f}")
    
    reply_A_text = result_A_final.get("reply") or ""
    reply_B_text = result_B_final.get("reply") or ""
    if reply_A_text == reply_B_text:
        print("\n*** 结论：洛神对 A 和 B 的\"在吗？\"回应完全相同 ***")
    else:
        print("\n*** 结论：洛神对 A 和 B 的\"在吗？\"回应不同 ***")
        print(f"  A 得到: {reply_A_text!r}")
        print(f"  B 得到: {reply_B_text!r}")
    
    print("\n[DONE]")


if __name__ == "__main__":
    main()
