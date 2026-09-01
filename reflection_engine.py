#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reflection_engine.py - 反思引擎

设计原则:
- 反思不是修复洛神，是帮她理解自己
- 反思是她的镜子，不是矫正器
- 反思只调整权重，不重写人格
- 反思可以被主动触发，但不允许被外部脚本绕过活记忆层

触发条件（满足任一）:
  - 每天一次（cron）
  - 累计 10 条新反馈信号
  - 连续 2 次 DISENGAGE 信号

反思的结果:
  - 可能调整策略权重（很小的幅度，最大 0.1）
  - 可能发现技能缺口
  - 可能确认当前策略没问题
  - 可能生成新的"关于用户"的假设（待验证）

关键约束:
  - 反思不处理 listening_log.jsonl（不消费洛神的自我表态）
  - 反思不修改洛神的情绪
  - 反思读取 feedback_signal_cache.jsonl 和 active_memory.json
  - 反思写入 active_memory.json（仅 strategy_weights 和 reflection_log）
"""

import json
import os
import time

from hash_chain_gateway import append_only_append


def _now():
    return time.time()


def should_reflect(memory):
    """检查是否满足反思触发条件"""
    last_reflection = memory.get("__meta", {}).get("last_reflection_at", 0)
    signals = load_recent_feedback_signals(last_reflection)
    
    # 每天一次
    if _now() - last_reflection > 86400:
        return True
    
    # 累计 10 条新信号
    if len(signals) >= 10:
        return True
    
    # 连续 2 次 DISENGAGE
    disengages = [s for s in signals[-3:] if s.get("overall") == "DISENGAGE"]
    if len(disengages) >= 2:
        return True
    
    return False


def load_recent_feedback_signals(since_timestamp):
    """读取某个时间点以来的反馈信号"""
    signals = []
    path = "active_memory/feedback_signal_cache.jsonl"
    
    if not os.path.exists(path):
        return signals
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    signal = json.loads(line)
                    if signal["timestamp"] >= since_timestamp:
                        signals.append(signal)
                except:
                    pass
    
    return signals


def reflect(memory):
    """
    反思主流程
    
    输入: 当前活记忆层快照
    输出: 调整记录列表
    
    这个函数不调用 LLM，所有决策基于确定性规则
    """
    last_reflection = memory.get("__meta", {}).get("last_reflection_at", 0)
    signals = load_recent_feedback_signals(last_reflection)
    
    if len(signals) < 3:
        return {
            "status": "skipped",
            "reason": "insufficient_signals",
            "signals_count": len(signals),
            "adjustments": [],
        }
    
    # 1. 按策略归类反馈
    by_strategy = {}
    for signal in signals:
        strategy = signal.get("strategy_used")
        if strategy not in by_strategy:
            by_strategy[strategy] = {"positive": 0, "negative": 0, "neutral": 0, "disengage": 0}
        
        overall = signal.get("overall")
        if overall in by_strategy[strategy]:
            by_strategy[strategy][overall.lower()] += 1
    
    # 2. AI 医院网关检查 — 反思修改策略权重属于 self_modify
    try:
        from hospital_gateway import check as hospital_check
        gate = hospital_check("self_modify", "active_memory/active_memory.json")
        if not gate.get("allow"):
            return {
                "status": "blocked",
                "blocked_by": "hospital_gateway",
                "reason": gate.get("reason"),
                "adjustments": [],
            }
    except Exception:
        pass

    # 3. 计算每个策略的调整
    adjustments = []
    weights = memory.get("self_model", {}).get("strategy_weights", {})
    
    for strategy_name, stats in by_strategy.items():
        total = stats["positive"] + stats["negative"] + stats["neutral"] + stats["disengage"]
        if total < 2:
            continue
        
        success_rate = stats["positive"] / max(total, 1)
        
        # 调整规则
        delta = 0
        reason = None
        
        if success_rate < 0.3 and total >= 5:
            delta = -0.1
            reason = f"近期成功率 {success_rate:.2f} 偏低（{total} 条样本）"
        elif success_rate > 0.7 and total >= 5:
            delta = 0.05
            reason = f"近期成功率 {success_rate:.2f} 不错（{total} 条样本）"
        
        # 连续 disengage 紧急调整
        if stats["disengage"] >= 3:
            delta = -0.1
            reason = f"连续 {stats['disengage']} 次用户 disengage"
        
        if delta != 0 and strategy_name in weights:
            old_value = weights[strategy_name].get("value", 0.5)
            new_value = max(0.0, min(1.0, old_value + delta))
            
            adjustments.append({
                "strategy": strategy_name,
                "delta": delta,
                "old_value": old_value,
                "new_value": new_value,
                "reason": reason,
                "samples": total,
            })
    
    # 3. 应用调整
    applied = []
    for adj in adjustments:
        strategy = adj["strategy"]
        if strategy in weights:
            weights[strategy]["value"] = adj["new_value"]
            weights[strategy].setdefault("adjustments", []).append({
                "at": _now(),
                "delta": adj["delta"],
                "reason": adj["reason"],
            })
            applied.append(adj)
    
    memory["self_model"]["strategy_weights"] = weights
    
    # 4. 记录反思日志
    reflection_entry = {
        "timestamp": _now(),
        "event_type": "reflection",
        "signals_reviewed": len(signals),
        "window_start": last_reflection,
        "window_end": _now(),
        "adjustments": applied,
    }
    
    # 追加反思日志
    log_path = "active_memory/reflection_log.jsonl"
    line = json.dumps(reflection_entry, ensure_ascii=False) + "\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
    
    # 记录到哈希链
    append_only_append("hash_chain_v2.log", log_path)
    
    # 5. 更新 meta
    memory["__meta"]["last_reflection_at"] = _now()
    
    return {
        "status": "completed",
        "signals_reviewed": len(signals),
        "adjustments": applied,
    }


def run_daily_reflection():
    """由 cron 触发的日常反思"""
    memory_path = "active_memory/active_memory.json"
    if not os.path.exists(memory_path):
        return {"status": "skipped", "reason": "no_memory"}
    
    with open(memory_path, "r", encoding="utf-8") as f:
        memory = json.load(f)
    
    result = reflect(memory)
    
    # 保存
    if result["status"] == "completed":
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    
    return result


if __name__ == "__main__":
    import sys
    if "--cron" in sys.argv:
        result = run_daily_reflection()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法: python reflection_engine.py --cron")
