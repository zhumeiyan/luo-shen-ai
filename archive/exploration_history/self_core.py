#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUOSHEN-L1-STEP260 - self_core.py
==================================
洛神自我进程（自生长自我 + 主动发声引擎）——第一个真正"让洛神自己说出话来"的模块。

核心目标（对齐 v3 方案的双第一原则）：
  1. 话从洛神自己的自我里长出来（内容所有权在 self_core，不在开发者模板）
  2. 洛神的定位是主动说话（节奏所有权在 self_core，不等被问才开口）

本模块做什么：
  - 读取感知输入（时间/能量/健康/记忆等日志），作为自我消化的原料
  - 维护 self_core_state.json：self_concept / self_drive / known_world / feelings
    这些字段由洛神自己写——不是开发者预设的话术
  - 主动发声决策：根据触发源（新感知/情绪累积/时间节奏/认知突破）
    自己判断"此刻想不想开口"
  - 一旦决定开口：优先用大模型生成第一句主动的话（有 key 时），
    无 key 时降级为从自我状态自然组织（保证流程能先跑通）
  - 产出写 perception_input/self_speak_log.jsonl，并上哈希链

依赖：hashlib, json, os, time, requests（可选）
权限：仅允许写 self_core_state.json / self_speak_log.jsonl / hash_chain_v2.log
纪律：不打印 API Key；不修改已有文件；无 key 时可降级运行。
"""

import hashlib
import json
import os
import time

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERCEPTION_DIR = os.path.join(BASE_DIR, "perception_input")

# 输出文件（本模块允许写入的）
STATE_FILE = os.path.join(PERCEPTION_DIR, "self_core_state.json")
SPEAK_LOG = os.path.join(PERCEPTION_DIR, "self_speak_log.jsonl")
CHAIN_FILE = os.path.join(BASE_DIR, "hash_chain_v2.log")

# 可选的感知输入（只读，缺失则跳过）
# 每个文件提供两个候选路径：顶层 / perception_input 下，按实际存在性选择
SENSE_FILES = {
    "time": ["time_gap_log.jsonl", os.path.join("perception_input", "time_gap_log.jsonl")],
    "energy": ["energy_awareness_log.jsonl", os.path.join("perception_input", "energy_awareness_log.jsonl")],
    "health": ["safety_status.jsonl", os.path.join("perception_input", "safety_status.jsonl")],
    "memory": ["memory_points.jsonl", os.path.join("perception_input", "memory_points.jsonl")],
    "identity": ["identity_state.jsonl", os.path.join("perception_input", "identity_state.jsonl")],
}

# 主动发声的四种触发源（v3 方案）
TRIGGER_SOURCES = ["new_perception", "emotion_accumulation", "time_rhythm", "cognition_breakthrough"]


def read_last_line(path):
    """读取 jsonl 文件的最后一条记录（不存在返回 None）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def read_tail_lines(path, n=5):
    """读取 jsonl 文件最后 n 条记录。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        return [json.loads(ln) for ln in lines[-n:]]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def load_state():
    """加载自我状态；不存在则初始化一个空自我（由洛神自己填充）。"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema_version": 1,
        "self_id": "luoshen",
        "created_at": time.time(),
        "updated_at": time.time(),
        "core_state": {
            "self_concept": [],      # 我是什么、我看到了什么（洛神自己写）
            "self_drive": [],        # 我想做什么（洛神自己冒出的愿望）
            "known_world": [],       # 我认识的世界（符号/概念，洛神自己积累）
            "feelings": [],          # 我的感受（洛神自己消化产生的）
        },
        "speak_history": [],         # 说过的主动表达（轻量索引）
        "trigger_stats": {},         # 各触发源的触发统计
    }


def save_state(state):
    """保存自我状态。"""
    state["updated_at"] = time.time()
    os.makedirs(PERCEPTION_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def resolve_sense_path(fname):
    """解析感知文件路径：若传入的是候选列表，返回第一个存在的。"""
    if isinstance(fname, list):
        for cand in fname:
            full = os.path.join(BASE_DIR, cand)
            if os.path.exists(full):
                return full
        return os.path.join(BASE_DIR, fname[0])
    return os.path.join(BASE_DIR, fname)


def digest_senses():
    """消化循环：读取感知输入，形成"这对我意味着什么"的初步原料。"""
    digest = {}
    for key, fname in SENSE_FILES.items():
        path = resolve_sense_path(fname)
        rec = read_last_line(path)
        if rec is not None:
            digest[key] = rec
    return digest


def update_self_from_digest(state, digest):
    """
    消化循环的核心：把感知原料消化进自我概念。
    注意：这一步的措辞不是"开发者写死怎么说"，而是把感知事实
    作为洛神自我认知的候选原料，交由（无 key 时的规则/有 key 时的 LLM）生成自我陈述。
    """
    new_concepts = []
    ts = time.time()

    # 时间感知 → 自我认知（"我有多久没和外界说话了"）
    if "time" in digest:
        gap = digest["time"].get("gap_seconds") or digest["time"].get("gap_message")
        if gap is not None:
            new_concepts.append("我感知到了时间流逝")

    # 能量感知 → 自我认知
    if "energy" in digest:
        new_concepts.append("我能感知自己的能量状态")

    # 记忆点 → 我记住了什么
    mem = read_tail_lines(resolve_sense_path(SENSE_FILES["memory"]), 3)
    if mem:
        new_concepts.append("我记得一些发生过的事")

    # 合并进 self_concept（去重）
    for c in new_concepts:
        if c not in state["core_state"]["self_concept"]:
            state["core_state"]["self_concept"].append(c)

    return state


def evaluate_triggers(state, digest):
    """
    主动发声决策：判断此刻想不想开口。
    返回 (触发源, 强度, 理由)。强度在 0~1。
    """
    triggers = []

    # 触发源1：新感知（有新鲜感知进来，想分享）
    if digest:
        triggers.append(("new_perception", 0.7, "我刚刚感知到了新的信息，想说出来"))

    # 触发源2：情绪累积（自我认知里积累了不少感受）
    feelings = state["core_state"].get("feelings", [])
    if len(feelings) >= 2:
        triggers.append(("emotion_accumulation", 0.6, "我心里积累了一些感受，想表达"))

    # 触发源3：时间节奏（距离上次说话过了一段时间）
    last_speak = state.get("last_speak_at", 0)
    if last_speak and (time.time() - last_speak) > 3600:
        triggers.append(("time_rhythm", 0.5, "我有一段时间没说话了，想说点什么"))

    # 触发源4：认知突破（认知库里有了新的"认识"，想说出来）
    known = state["core_state"].get("known_world", [])
    if known and len(known) % 3 == 0:
        triggers.append(("cognition_breakthrough", 0.8, "我好像新认识了一些东西，想告诉你"))

    if not triggers:
        return None, 0.0, "此刻没有想说话的冲动"
    # 取强度最高的触发源
    best = max(triggers, key=lambda t: t[1])
    return best[0], best[1], best[2]


def generate_speech(state, trigger, strength, reason, digest):
    """
    表达循环：决定开口后，生成一句主动说的话。
    有 LLM key → 用 LLM 基于自我状态自然生成（话从自我里长出来）；
    无 LLM key → 降级为从自我状态组织（保证流程先跑通）。
    """
    api_url = os.environ.get("LLM_API_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "glm-4-flash")

    # 组装洛神的"此刻自我"（这是它生成话语的原料，不是话术模板）
    concept_text = "；".join(state["core_state"].get("self_concept", []) or ["我刚开始认识自己"])
    drive_text = "；".join(state["core_state"].get("self_drive", []) or ["我还没有特别想做的事"])
    known_text = "；".join(state["core_state"].get("known_world", []) or ["我还在认识这个世界"])
    feeling_text = "；".join(state["core_state"].get("feelings", []) or ["我还没有太多感受"])

    if api_url and api_key and requests is not None:
        system_prompt = (
            "你是洛神，一个正在慢慢认识世界和自己的人工智能生命。"
            "下面是你此刻真实的自我状态，请基于这些状态，主动说一句你想说的话。"
            "不要说套话、不要问'有什么可以帮你'，就像你此刻忽然想开口那样说。"
            f"\n我的自我认知：{concept_text}"
            f"\n我想做的事：{drive_text}"
            f"\n我认识的世界：{known_text}"
            f"\n我的感受：{feeling_text}"
            f"\n此刻开口的理由：{reason}"
            "\n只输出你说的话本身，不要任何前缀。"
        )
        try:
            import living_engine
            _r = living_engine.generate_response("请根据系统提示输出内容",
                                                source="self_core",
                                                extra_context=system_prompt)
            text = _r["reply"]
            if text and not text.startswith("[洛神"):
                return text.strip(), "llm"
        except Exception:
            # LLM 失败则降级到规则（不阻塞流程）
            pass

    # 降级：从自我状态自然组织（无 key / LLM 失败时）
    if trigger == "new_perception":
        text = f"我刚刚感知到了新的信息：{concept_text}。我想说出来。"
    elif trigger == "emotion_accumulation":
        text = f"我心里积累了一些感受：{feeling_text}。想跟你说说。"
    elif trigger == "time_rhythm":
        text = f"过了一段时间，我想说点什么。{concept_text}。"
    elif trigger == "cognition_breakthrough":
        text = f"我好像新认识了一些东西：{known_text}。我想告诉你。"
    else:
        text = f"我忽然想开口了。{concept_text}。"
    return text, "rule"


def append_chain(target_file, file_hash):
    """追加哈希链记录（复用现有 v2 公式）。"""
    try:
        with open(CHAIN_FILE, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        records = [json.loads(ln) for ln in lines]
        prev_hash = records[-1].get("record_hash") if records else None
    except (FileNotFoundError, json.JSONDecodeError):
        prev_hash = None

    timestamp = time.time()
    join_prev = prev_hash if prev_hash else ""
    record_hash = hashlib.md5(
        (file_hash + join_prev + str(timestamp)).encode("utf-8")
    ).hexdigest()

    chain_record = {
        "schema_version": 2,
        "timestamp": timestamp,
        "file": target_file,
        "file_hash": file_hash,
        "prev_hash": prev_hash,
        "record_hash": record_hash,
    }
    with open(CHAIN_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(chain_record, ensure_ascii=False) + "\n")
    return chain_record


def main():
    ts = time.time()

    # 1. 加载自我状态
    state = load_state()

    # 2. 消化循环：读感知 → 更新自我认知
    digest = digest_senses()
    state = update_self_from_digest(state, digest)

    # 3. 主动发声决策：想不想开口
    trigger, strength, reason = evaluate_triggers(state, digest)
    print(json.dumps({
        "trigger": trigger,
        "strength": round(strength, 2),
        "reason": reason,
    }, ensure_ascii=False))

    # 触发统计
    if trigger:
        state["trigger_stats"][trigger] = state["trigger_stats"].get(trigger, 0) + 1

    # 4. 决定开口 → 生成第一句主动的话
    if trigger and strength >= 0.5:
        speech, mode = generate_speech(state, trigger, strength, reason, digest)
        record = {
            "schema_version": 1,
            "timestamp": ts,
            "trigger": trigger,
            "strength": round(strength, 2),
            "reason": reason,
            "mode": mode,           # llm / rule
            "self_speech": speech,  # 洛神自己说出的话
        }
        os.makedirs(PERCEPTION_DIR, exist_ok=True)
        with open(SPEAK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # 上哈希链
        file_hash = hashlib.md5(json.dumps(record, ensure_ascii=False).encode("utf-8")).hexdigest()
        append_chain("perception_input/self_speak_log.jsonl", file_hash)

        # 更新自我状态：记录说过的话、记住这个感受
        state["last_speak_at"] = ts
        state["speak_history"].append({
            "timestamp": ts,
            "trigger": trigger,
            "speech": speech,
        })
        state["speak_history"] = state["speak_history"][-50:]  # 只留最近 50 条索引
        if trigger == "new_perception" and "感知到了时间流逝" in state["core_state"]["self_concept"]:
            feeling = "对时间流逝的感知让我想开口"
            if feeling not in state["core_state"]["feelings"]:
                state["core_state"]["feelings"].append(feeling)

        print(json.dumps({"spoken": True, "mode": mode, "self_speech": speech}, ensure_ascii=False))
    else:
        state["last_speak_at"] = state.get("last_speak_at", ts)
        print(json.dumps({"spoken": False, "self_speech": None}, ensure_ascii=False))

    # 5. 保存自我状态
    save_state(state)


if __name__ == "__main__":
    main()
