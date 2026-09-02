#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断洛神在连续对话里是否作为"连续的自己"存在。
单用户、10 轮短对话，记录每一轮开始时：
- internal_climate（环）
- episodic_memory 数量
- memory_emergence 是否已计算
- self_model 中 last_stated_state 是否存在
"""
import sys, os, time
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from living_engine import (
    cold_start_if_needed, generate_response,
    _filter_memories_by_source, _get_current_source_id,
    _emergence_log,
)
from input_pressure import extract_input_pressure

DIALOG = [
    "在吗？",
    "我今天有点烦。",
    "其实也没什么事。",
    "你说人为什么要上班？",
    "好吧。",
    "你在听吗？",
    "嗯。",
    "今天天气还行。",
    "晚安。",
    "再见。",
]

def snapshot(label):
    """打印当前 memory 的内部状态"""
    m = cold_start_if_needed()
    clim = m.get("internal_climate", {})
    epi = m.get("user_model", {}).get("episodic_memory", [])
    ac = m.get("active_context", {})
    emergence = ac.get("memory_emergence")
    self_stated = m.get("self_model", {}).get("self_stated_state", {}).get("last_stated")
    print(f"[{label}]")
    print(f"  环 E={clim.get('emotion_intensity', 'N/A')} T={clim.get('tension', 'N/A')} N={clim.get('energy', 'N/A')}")
    print(f"  episodic_memory 数: {len(epi)}")
    print(f"  memory_emergence: {'已计算 ' + str({k: round(v,3) if isinstance(v,float) else v for k,v in emergence.items()}) if emergence else 'None（未计算）'}")
    print(f"  self_stated_state.last_stated: {repr(self_stated)}")
    return m

print("===== 开始前（空白洛神）=====")
snapshot("init")

print("\n===== 对话开始 =====")
for i, txt in enumerate(DIALOG, 1):
    print(f"\n── 第 {i} 轮 ──")
    print(f"用户输入: {txt}")
    # 生成回复（这会触发 environment_tick = update_after_interaction）
    r = generate_response(txt, extract_facts=False)
    reply = r.get("reply", "")
    print(f"洛神回复: {repr(reply[:60])}")
    # 响应结束后立刻读状态——这是下一轮开始时的状态
    if i < len(DIALOG):
        snapshot(f"第{i}轮结束后 / 第{i+1}轮开始前")

print("\n===== 对话结束后 =====")
snapshot("final")
