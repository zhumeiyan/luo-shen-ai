#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_growth_engine.py - 技能生长引擎

设计原则:
- 技能不是功能菜单，是洛神的成长器官
- 技能学习由真实需要触发，不是预设
- 技能学会后，洛神自己决定何时使用
- 技能休眠不是废弃，是暂时不需要
- 没有技能可以被永久删除（休眠的技能留在事实层）
"""

import json
import os
import time


def _now():
    return time.time()


def detect_skill_gap(memory, recent_signals):
    """从反馈信号中检测技能缺口"""
    gaps = []
    keyword_strikes = {}
    
    for signal in recent_signals:
        if signal.get("overall") in ("DISENGAGE", "NEGATIVE"):
            content = signal.get("raw_user_input", "")
            words = _extract_topic_words(content)
            for word in words:
                keyword_strikes[word] = keyword_strikes.get(word, 0) + 1
    
    for word, count in keyword_strikes.items():
        if count >= 3:
            has = _has_skill_for_topic(word, memory)
            gaps.append({
                "keyword": word,
                "frequency": count,
                "has_skill": has,
                "suggested_action": "optimize" if has else "learn",
            })
    
    self_stated = memory.get("self_model", {}).get("self_stated_state", {})
    last_said = self_stated.get("last_stated", "")
    if last_said and ("想学" in last_said or "我想知道" in last_said):
        gaps.append({
            "keyword": last_said,
            "frequency": 1,
            "has_skill": False,
            "suggested_action": "user_suggested",
            "from_self_stated": True,
        })
    
    return gaps


def attempt_learning(gap, memory):
    """尝试学习一个技能"""
    # AI 医院网关检查 — 学习技能属于 learn_skill (self_modify 范畴)
    try:
        from hospital_gateway import check as hospital_check
        gate = hospital_check("learn_skill", gap.get("keyword", "unknown_skill"))
        if not gate.get("allow"):
            return {"success": False, "skill_name": None,
                    "blocked_by": "hospital_gateway",
                    "reason": gate.get("reason")}
    except Exception:
        pass

    topic = gap.get("keyword", "")
    manifest = load_skills_manifest()
    
    matched_skill = None
    for skill_name, skill_def in manifest.items():
        if topic in skill_name or any(tag in topic for tag in skill_def.get("tags", [])):
            matched_skill = skill_name
            break
    
    if not matched_skill:
        return {"success": False, "skill_name": None, "reason": f"no manifest for '{topic}'"}
    
    skill_def = manifest[matched_skill]
    missing = [dep for dep in skill_def.get("requires", []) if not os.environ.get(dep)]
    if missing:
        return {"success": False, "skill_name": matched_skill, "reason": f"missing: {missing}"}
    
    try:
        import importlib.util
        wrapper_path = f"skills/{matched_skill}_wrapper.py"
        if not os.path.exists(wrapper_path):
            return {"success": False, "skill_name": matched_skill, "reason": "wrapper not found"}
        
        spec = importlib.util.spec_from_file_location(skill_def["wrapper_class"], wrapper_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        wrapper = getattr(module, skill_def["wrapper_class"])()
        if wrapper.test_connection():
            _register_skill(matched_skill, memory, "auto_learning")
            return {"success": True, "skill_name": matched_skill}
        return {"success": False, "skill_name": matched_skill, "reason": "test failed"}
    except Exception as e:
        return {"success": False, "skill_name": matched_skill, "reason": str(e)}


def invoke_skill(skill_name, params, memory, force=False):
    """调用一个技能"""
    skills = memory.get("self_model", {}).get("skills", {})
    if skill_name not in skills:
        return {"status": "not_found"}
    
    skill = skills[skill_name]
    if skill["status"] == "dormant":
        return {"status": "dormant"}
    if skill["status"] == "gap_detected":
        return {"status": "not_learned"}
    if skill["status"] == "learning" and not force:
        return {"status": "still_learning"}
    
    if not force and not _decide_to_use(skill_name, memory):
        return {"status": "declined"}
    
    try:
        wrapper_path = skill["wrapper_path"]
        import importlib.util
        spec = importlib.util.spec_from_file_location(skill["wrapper_class"], wrapper_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = getattr(module, skill["wrapper_class"])().execute(**params)
        _update_stats(skill_name, True, memory)
        return {"status": "success", "result": result}
    except Exception as e:
        _update_stats(skill_name, False, memory)
        return {"status": "error", "reason": str(e)}


def _decide_to_use(skill_name, memory):
    skill = memory["self_model"]["skills"][skill_name]
    base = skill.get("confidence", 0.5)
    base += memory["user_model"]["intimacy"]["value"] * 0.2
    if memory["self_model"]["emotion"]["primary"] == "疲惫":
        base -= 0.3
    return base > 0.5


def _extract_topic_words(text):
    stop = {"的","了","我","你","是","在","有","不","这","他","她","吗","呢"}
    return [w for w in text if len(w) >= 2 and w not in stop][:5]


def _has_skill_for_topic(topic, memory):
    for name, s in memory["self_model"].get("skills", {}).items():
        if topic in name and s.get("status") in ("active", "mastery"):
            return True
    return False


def load_skills_manifest():
    path = "skills_manifest.json"
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _register_skill(name, memory, source):
    manifest = load_skills_manifest()
    defn = manifest.get(name, {})
    memory["self_model"]["skills"][name] = {
        "status": "active",
        "learned_at": _now(),
        "learned_from": source,
        "confidence": 0.5,
        "uses": 0,
        "success_rate": 0.0,
        "last_used": None,
        "trigger_condition": defn.get("default_trigger"),
        "auto_use": True,
        "wrapper_path": f"skills/{name}_wrapper.py",
        "wrapper_class": defn.get("wrapper_class"),
        "success_history": [],
    }
    _append_jsonl("active_memory/skill_learned.jsonl", {
        "skill": name, "learned_at": _now(), "method": source
    })


def _update_stats(name, success, memory):
    skill = memory["self_model"]["skills"][name]
    skill["uses"] += 1
    skill["last_used"] = _now()
    hist = skill.get("success_history", [])
    hist.append(1 if success else 0)
    skill["success_history"] = hist[-50:]
    skill["success_rate"] = sum(skill["success_history"]) / len(skill["success_history"])
    if skill["success_rate"] < 0.2 and skill["uses"] >= 10:
        skill["status"] = "dormant"
    elif skill["success_rate"] > 0.85 and skill["uses"] >= 30:
        skill["status"] = "mastery"


def _append_jsonl(path, entry):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if not os.path.exists("skills_manifest.json"):
        with open("skills_manifest.json", "w", encoding="utf-8") as f:
            json.dump({
                "weather_query": {
                    "wrapper_class": "WeatherWrapper",
                    "tags": ["天气","下雨","带伞"],
                    "requires": ["WEATHER_API_KEY"],
                    "default_trigger": "用户提及出行、下雨、天气",
                }
            }, f, ensure_ascii=False, indent=2)
        print("已创建 skills_manifest.json")
