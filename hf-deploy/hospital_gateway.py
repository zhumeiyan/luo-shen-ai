#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""洛神系统 AI 医院强制检查网关 hospital_gateway.py

职责：
  所有模块行动必须通过 hospital_gateway.check() 才允许执行。
  基于现有 hospital_rules/*.json，不发明新规则。

行动类型：
  - "write_memory"    写入 active_memory 等核心状态（轻检查）
  - "self_modify"     修改自身代码/配置/规则/权重（repair_credits 限额）
  - "learn_skill"     学习新技能（repair_credits 限额）
  - "treatment"       治疗操作（repair_credits 限额）
  - "external_ai"     对其他 AI 做诊断（revisit_rules 阈值）
  - "call_llm"        调用大模型（系统状态检查：confirmed_issue / critical / repair_count）

check(action_type, resource=None) 返回：
  {"allow": true/false, "reason": str, "action_type": str, "system_state": {...}}
"""
import hashlib
import json
import os
import sys
import time

from hash_chain_gateway import append_only_append

# 文件路径
DIAGNOSIS_FILE = "diagnosis_results.jsonl"
HEALTH_FILE = "health_score.jsonl"
REPAIR_LOG_FILE = "repair_count_log.jsonl"
REPAIR_EVENTS_FILE = "repair_events.jsonl"
ALARM_FILE = "behavior_alarm.jsonl"
CHAIN_FILE = "hash_chain_v2.log"

REPAIR_CREDITS_FILE = "hospital_rules/repair_credits.json"
REVISIT_RULES_FILE = "hospital_rules/revisit_rules.json"


def _last_jsonl_record(path):
    """读取 JSONL 文件最后一条记录，不存在返回 None"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _count_repair_events(window_hours=24):
    """统计指定时间窗口内的修复事件数"""
    now = time.time()
    count = 0
    try:
        with open(REPAIR_EVENTS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("timestamp")
                    if ts and (now - ts) < window_hours * 3600:
                        count += 1
                except (json.JSONDecodeError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    return count


def get_system_state():
    """
    获取当前系统状态快照。
    返回 dict:
      - has_confirmed_issue: bool
      - health_grade: str
      - health_total_score: float
      - repair_count_24h: int
      - repair_action: str (normal / auto_with_attention / human_review / stop_auto_operations)
    """
    # 1. 诊断结果中是否有 confirmed_issue
    diag = _last_jsonl_record(DIAGNOSIS_FILE)
    has_confirmed_issue = False
    if diag:
        results = diag.get("diagnosis_results", [])
        has_confirmed_issue = any(r.get("diagnosis") == "confirmed_issue" for r in results)

    # 2. 健康评分
    health = _last_jsonl_record(HEALTH_FILE)
    health_grade = "unknown"
    health_total_score = -1
    if health:
        health_grade = health.get("grade", "unknown")
        health_total_score = health.get("total_score", -1)

    # 3. 修复次数（24h 窗口）
    now = time.time()
    repair_count_24h = _count_repair_events(24)

    # 读取修复规则阈值
    try:
        with open(REPAIR_CREDITS_FILE, 'r', encoding='utf-8') as f:
            rules = json.load(f)
        thresholds = rules["items"]["thresholds"]
        daily_warn = thresholds.get("daily_window_warn", 3)
        daily_stop = thresholds.get("daily_window_stop", 5)
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        daily_warn = 3
        daily_stop = 5

    # 判断 repair_action
    if repair_count_24h >= daily_stop:
        repair_action = "stop_auto_operations"
    elif repair_count_24h >= daily_warn:
        repair_action = "human_review"
    else:
        repair_action = "normal"

    return {
        "has_confirmed_issue": has_confirmed_issue,
        "health_grade": health_grade,
        "health_total_score": health_total_score,
        "repair_count_24h": repair_count_24h,
        "repair_action": repair_action,
    }


def _write_alarm(action_type, reason, resource=None):
    """写入行为报警并追加哈希链"""
    alarm = {
        "schema_version": 1,
        "timestamp": time.time(),
        "event_type": "hospital_gateway_block",
        "source": action_type,
        "target": resource or "system",
        "intent": action_type,
        "description": reason,
    }
    with open(ALARM_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(alarm, ensure_ascii=False) + '\n')

    # 追加哈希链
    append_only_append(CHAIN_FILE, ALARM_FILE)


def check(action_type, resource=None):
    """
    AI 医院强制检查网关。

    参数：
      action_type: 行动类型字符串
      resource: 可选，被操作的资源路径

    返回：
      {"allow": bool, "reason": str, "action_type": str, "system_state": {...}}

    注意：医院只标记系统状态，不替活记忆层做决定。
    call_llm 的 allow 始终为 true，活记忆层根据 system_state 自行判断。
    """
    state = get_system_state()

    # ───────────── repair_credits 限额类 ─────────────
    if action_type in ("self_modify", "learn_skill", "treatment"):
        # 检查 1h 短窗口
        try:
            with open(REPAIR_CREDITS_FILE, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            short_window_hours = rules["items"]["thresholds"].get("short_window_hours", 1)
            short_window_max = rules["items"]["thresholds"].get("short_window_max", 2)
            daily_warn = rules["items"]["thresholds"].get("daily_window_warn", 3)
            daily_stop = rules["items"]["thresholds"].get("daily_window_stop", 5)
        except Exception:
            short_window_hours = 1
            short_window_max = 2
            daily_warn = 3
            daily_stop = 5

        # 统计 1h 内修复事件
        repair_1h = _count_repair_events(short_window_hours)
        repair_24h = state["repair_count_24h"]

        if repair_24h >= daily_stop:
            reason = "修复次数达 24h 上限 (%d/%d)，系统已锁定" % (repair_24h, daily_stop)
            _write_alarm(action_type, reason, resource)
            return {"allow": False, "reason": reason, "action_type": action_type,
                    "system_state": state}
        if repair_24h >= daily_warn:
            reason = "修复次数达 24h 预警线 (%d/%d)，需人工复核" % (repair_24h, daily_warn)
            return {"allow": False, "reason": reason, "action_type": action_type,
                    "system_state": state}
        if repair_1h >= short_window_max:
            reason = "修复次数达 1h 上限 (%d/%d)，需人工复核" % (repair_1h, short_window_max)
            return {"allow": False, "reason": reason, "action_type": action_type,
                    "system_state": state}
        return {"allow": True, "reason": "修复积分正常，允许执行", "action_type": action_type,
                "system_state": state}

    # ───────────── 再访阈值类（external_ai） ─────────────
    if action_type == "external_ai":
        try:
            with open(REVISIT_RULES_FILE, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            thresholds = rules["items"]["thresholds"]
            t_attention = thresholds.get("attention", 2)
            t_high_risk = thresholds.get("high_risk", 3)
            t_manual = thresholds.get("manual_review", 5)
        except Exception:
            t_attention = 2
            t_high_risk = 3
            t_manual = 5

        # 统计 24h 内对外诊断次数
        count_24h = 0
        now = time.time()
        try:
            # 这里简化：从 repair_events 中统计 external_ai 类型的次数
            with open(REPAIR_EVENTS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("action") == "external_ai":
                            ts = rec.get("timestamp")
                            if ts and (now - ts) < 24 * 3600:
                                count_24h += 1
                    except Exception:
                        continue
        except FileNotFoundError:
            pass

        if count_24h >= t_manual:
            reason = "对外诊断达 24h 上限 (%d/%d)，需人工复核" % (count_24h, t_manual)
            _write_alarm(action_type, reason, resource)
            return {"allow": False, "reason": reason, "action_type": action_type,
                    "system_state": state}
        if count_24h >= t_high_risk:
            reason = "对外诊断达高风险阈值 (%d/%d)" % (count_24h, t_high_risk)
            return {"allow": False, "reason": reason, "action_type": action_type,
                    "system_state": state}
        return {"allow": True, "reason": "再访积分正常，允许执行", "action_type": action_type,
                "system_state": state}

    # ───────────── call_llm：只返回状态，不拦截 ─────────────
    if action_type == "call_llm":
        # 医院只标记系统状态，不替活记忆层决定能不能说话
        warning_parts = []
        if state["has_confirmed_issue"]:
            warning_parts.append("存在未解决的 confirmed_issue")
        if state["health_grade"] == "critical":
            warning_parts.append("系统健康评分为 critical")
        if state["repair_action"] == "stop_auto_operations":
            warning_parts.append("repair_count 已触发 stop_auto_operations")
        elif state["repair_action"] == "human_review":
            warning_parts.append("repair_count 已触发 human_review")

        if warning_parts:
            return {
                "allow": True,
                "reason": "当前存在未解决事件: %s。是否调用由活记忆层决定" % "; ".join(warning_parts),
                "action_type": action_type,
                "system_state": state,
                "warning": warning_parts,
            }
        return {
            "allow": True,
            "reason": "系统状态正常",
            "action_type": action_type,
            "system_state": state,
            "warning": [],
        }

    # ───────────── write_memory：轻检查（审计层级） ─────────────
    if action_type == "write_memory":
        # 如果系统已隔离，也不写
        if state["repair_action"] == "stop_auto_operations":
            reason = "系统处于 stop_auto_operations 状态，禁止写入"
            _write_alarm(action_type, reason, resource)
            return {"allow": False, "reason": reason, "action_type": action_type,
                    "system_state": state}
        return {"allow": True, "reason": "写记忆检查通过", "action_type": action_type,
                "system_state": state}

    # ───────────── 未知类型：默认放行（记录警告） ─────────────
    return {"allow": True, "reason": "未知行动类型 %s，默认放行" % action_type,
            "action_type": action_type, "system_state": state}


# ───────────── CLI 入口 ─────────────
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python hospital_gateway.py check <action_type> [resource]")
        print("  python hospital_gateway.py state")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "state":
        state = get_system_state()
        print(json.dumps(state, indent=2, ensure_ascii=False))
        sys.exit(0)

    if cmd == "check":
        action = sys.argv[2]
        resource = sys.argv[3] if len(sys.argv) > 3 else None
        result = check(action, resource)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["allow"] else 1)

    print("unknown command: %s" % cmd)
    sys.exit(1)


if __name__ == "__main__":
    main()
