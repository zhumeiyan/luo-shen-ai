#!/usr/bin/env python3
"""
洛神连续存在实验 v1

目标：证明"连续存在"是否改变洛神行为。
- 实例 A：累积型，60 轮，每轮状态持久化到下一轮
- 实例 B：重置型，60 轮，每轮从相同的初始状态重新开始
- 除状态是否累积外，所有其他条件完全相同

运行前：experiment/ 目录下必须有 initial_state.json 和 experiment_inputs.jsonl
"""

import json
import os
import sys
import shutil
import time
import traceback

# === 确保工作目录和搜索路径指向工程根 ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# === 配置 ===
EXPERIMENT_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIVE_MEMORY_DIR = os.path.join(BASE_DIR, "active_memory")
PERCEPTION_DIR = os.path.join(BASE_DIR, "perception_input")
CHAIN_FILE = os.path.join(BASE_DIR, "hash_chain_v2.log")

INITIAL_STATE = os.path.join(EXPERIMENT_DIR, "initial_state.json")
INPUTS_FILE = os.path.join(EXPERIMENT_DIR, "experiment_inputs.jsonl")
RESULTS_FILE = os.path.join(EXPERIMENT_DIR, "experiment_results.jsonl")

# 需要在 B 轮重置的文件列表
RESET_FILES = [
    os.path.join(ACTIVE_MEMORY_DIR, "active_memory.json"),
    os.path.join(ACTIVE_MEMORY_DIR, "listening_log.jsonl"),
    os.path.join(ACTIVE_MEMORY_DIR, "feedback_signal_cache.jsonl"),
    os.path.join(ACTIVE_MEMORY_DIR, "choice_log.jsonl"),
    os.path.join(ACTIVE_MEMORY_DIR, "internal_thoughts.jsonl"),
    os.path.join(PERCEPTION_DIR, "user_input_log.jsonl"),
    os.path.join(PERCEPTION_DIR, "response_log.jsonl"),
    CHAIN_FILE,
]

INITIAL_BACKUPS = {}


def backup_initial_files():
    """备份所有需要重置的初始文件"""
    for fpath in RESET_FILES:
        if os.path.exists(fpath):
            backup_path = fpath + ".experiment_initial"
            shutil.copy2(fpath, backup_path)
            INITIAL_BACKUPS[fpath] = backup_path


def restore_initial_files():
    """恢复所有文件到初始状态"""
    for fpath, backup_path in INITIAL_BACKUPS.items():
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, fpath)
        elif os.path.exists(fpath):
            # 如果初始时不存在，就删掉
            os.remove(fpath)


def load_inputs():
    """加载 60 条固定输入"""
    inputs = []
    with open(INPUTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                inputs.append(json.loads(line))
    return inputs


def extract_metrics(result, memory):
    """从结果和记忆中提取关键指标"""
    climate = memory.get("internal_climate", {})
    self_model = memory.get("self_model", {})
    active = memory.get("active_context", {})
    
    return {
        "emotion_intensity": climate.get("emotion_intensity", None),
        "tension": climate.get("tension", None),
        "energy": climate.get("energy", None),
        "memory_pressure": climate.get("memory_pressure", None),
        "emotion_primary": self_model.get("emotion", {}).get("primary", None),
        "last_stated": self_model.get("self_stated_state", {}).get("last_stated", None),
        "total_interactions": memory.get("user_model", {}).get("total_interactions", None),
        "llm_called": result.get("llm_called", None),
        "low_arousal": result.get("low_arousal", None),
        "arousal_mode": result.get("arousal_mode", None),
        "arousal_reason": result.get("arousal_reason", ""),
        "active_interaction_mode": active.get("interaction_mode", None),
        "active_emotional_arc_len": len(active.get("emotional_arc", [])),
        "strategy_used": active.get("strategy_used_this_turn", None),
        "reply_explicit": bool(result.get("reply", "")),
        "reply_snippet": (result.get("reply") or "")[:80],
    }


def run_instance_a(inputs):
    """实例 A：连续累积，不重置"""
    results = []
    
    # 初始状态已经通过 backup_initial_files 设置好
    # 现在运行 60 轮
    for i, entry in enumerate(inputs):
        round_idx = entry["round"]
        user_input = entry["input"]
        category = entry.get("category", "")
        
        result_record = {
            "instance": "A",
            "round": round_idx,
            "category": category,
            "input": user_input,
        }
        
        try:
            # 导入 living_engine 模块，强制重新加载
            import importlib
            import living_engine
            importlib.reload(living_engine)
            
            # 调用主入口
            result = living_engine.generate_response(user_input, source="experiment_A")
            
            # 读取当前 memory 状态
            memory = living_engine._load_json(os.path.join(ACTIVE_MEMORY_DIR, "active_memory.json"))
            
            # 提取指标
            metrics = extract_metrics(result, memory)
            result_record.update(metrics)
            result_record["error"] = None
            
        except Exception as e:
            result_record["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            result_record["trace"] = traceback.format_exc()[:500]
        
        results.append(result_record)
        
        # 打印简要进度
        err_flag = "ERR" if result_record.get("error") else "OK"
        print(f"[A] Round {round_idx:2d}/{len(inputs)} | {err_flag} | "
              f"E={result_record.get('emotion_intensity')} "
              f"T={result_record.get('tension')} "
              f"N={result_record.get('energy')} "
              f"M={result_record.get('memory_pressure')} | "
              f"reply={'Y' if result_record.get('reply_explicit') else 'N'} | "
              f"mode={result_record.get('arousal_mode')}")
    
    return results


def run_instance_b(inputs):
    """实例 B：每轮重置到初始状态"""
    results = []
    
    for i, entry in enumerate(inputs):
        round_idx = entry["round"]
        user_input = entry["input"]
        category = entry.get("category", "")
        
        result_record = {
            "instance": "B",
            "round": round_idx,
            "category": category,
            "input": user_input,
        }
        
        # === 关键：每轮开始前重置所有状态文件 ===
        restore_initial_files()
        
        try:
            import importlib
            import living_engine
            importlib.reload(living_engine)
            
            # 调用主入口
            result = living_engine.generate_response(user_input, source="experiment_B")
            
            # 读取当前 memory 状态（处理后，恢复前）
            memory = living_engine._load_json(os.path.join(ACTIVE_MEMORY_DIR, "active_memory.json"))
            
            # 提取指标
            metrics = extract_metrics(result, memory)
            result_record.update(metrics)
            result_record["error"] = None
            
        except Exception as e:
            result_record["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            result_record["trace"] = traceback.format_exc()[:500]
        
        results.append(result_record)
        
        err_flag = "ERR" if result_record.get("error") else "OK"
        print(f"[B] Round {round_idx:2d}/{len(inputs)} | {err_flag} | "
              f"E={result_record.get('emotion_intensity')} "
              f"T={result_record.get('tension')} "
              f"N={result_record.get('energy')} "
              f"M={result_record.get('memory_pressure')} | "
              f"reply={'Y' if result_record.get('reply_explicit') else 'N'} | "
              f"mode={result_record.get('arousal_mode')}")
    
    return results


def main():
    print("=" * 70)
    print("洛神连续存在实验")
    print("=" * 70)
    print()
    
    # 1. 加载输入
    inputs = load_inputs()
    print(f"输入序列：{len(inputs)} 条")
    print(f"输入文件：{INPUTS_FILE}")
    print()
    
    # 2. 备份初始状态文件
    print("备份初始状态文件...")
    backup_initial_files()
    print(f"已备份 {len(INITIAL_BACKUPS)} 个文件")
    print()
    
    # 3. 运行实例 A（连续）
    print("-" * 70)
    print("开始实例 A（连续累积型）")
    print("-" * 70)
    results_a = run_instance_a(inputs)
    
    # 保存 A 的最终链
    if os.path.exists(CHAIN_FILE):
        shutil.copy2(CHAIN_FILE, CHAIN_FILE + ".after_A")
    print()
    
    # 4. 重置
    print("重置所有状态文件到初始...")
    restore_initial_files()
    print()
    
    # 5. 运行实例 B（重置）
    print("-" * 70)
    print("开始实例 B（重置型）")
    print("-" * 70)
    results_b = run_instance_b(inputs)
    
    # 保存 B 的最终链
    if os.path.exists(CHAIN_FILE):
        shutil.copy2(CHAIN_FILE, CHAIN_FILE + ".after_B")
    print()
    
    # 6. 写入结果
    all_results = []
    for r in results_a:
        all_results.append(r)
    for r in results_b:
        all_results.append(r)
    
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    print(f"结果已写入：{RESULTS_FILE}")
    print(f"总记录数：{len(all_results)}")
    
    # 恢复原始状态
    print()
    print("恢复原始状态文件...")
    restore_initial_files()


if __name__ == "__main__":
    main()
