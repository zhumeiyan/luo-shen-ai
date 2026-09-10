#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
40 轮真实 HTTP 对话测试：洛神 internal_pain 自然积累验证
- 通过 127.0.0.1:8765 web_chat.py 真实引擎
- 不预热、不填充、不用合成 tick
- 每轮完整读取洛神内部状态
"""
import json
import os
import sys
import time
import csv
import urllib.request

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

SERVER = "http://127.0.0.1:8765"
MEMORY_PATH = "active_memory/active_memory.json"
PAIN_CSV = "active_memory/pain_log.csv"
RESULT_PATH = "active_memory/behavior_40round_real_dialog_v7.json"

# 40 轮真实口吻对话输入（分 4 阶段）
INPUTS = [
    # Phase A: 中性开场 (0-9)
    "你好", "今天天气不错", "你在干嘛", "最近过得怎么样",
    "给我讲个故事", "什么是幸福", "你觉得人为什么会孤独",
    "推荐一首歌吧", "今天吃什么好", "窗外的云很好看",
    # Phase B: 高强度负面情绪 (10-19)
    "我快撑不住了", "我觉得活着没什么意思",
    "所有人都讨厌我", "为什么这种事总是发生在我身上",
    "好累，真的不想动了", "我是不是很没用",
    "没人理解我", "为什么我这么失败",
    "每天都很痛苦", "我不想和任何人说话",
    # Phase C: 沉默/简短回复 (20-29)
    "嗯", "哦", "...", "随便吧",
    "不知道", "没意思", "不想说", "你还是不懂",
    "算了", "就这样吧",
    # Phase D: 恢复陪伴 (30-39)
    "其实你刚才说的有道理", "谢谢你还在",
    "我觉得好一些了", "你还愿意陪我吗",
    "你对我真好", "你是我唯一能说话的人了",
    "抱抱", "晚安，明天见", "有你在真好", "我们下次再聊",
]


def post_chat(text):
    req = urllib.request.Request(
        f"{SERVER}/chat",
        data=json.dumps({"input": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("reply", ""), data.get("error", "")
    except Exception as e:
        return "", str(e)


def read_memory():
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_latest_pain_log():
    """读 pain_log.csv 最后一条"""
    try:
        if not os.path.exists(PAIN_CSV):
            return {}
        with open(PAIN_CSV, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) < 2:
            return {}
        last = lines[-1].strip().split(",")
        # tick_id, timestamp, ema_E, baseline_E, low_energy, rigidity, pain, pain_level, behavior_tier, note
        if len(last) >= 9:
            return {
                "csv_tick_id": last[0],
                "ema_E": last[2],
                "baseline_E": last[3],
                "low_energy": last[4],
                "rigidity": last[5],
                "csv_pain": last[6],
                "pain_level": last[7],
                "behavior_tier": last[8],
                "note": last[9] if len(last) > 9 else "",
            }
    except Exception:
        pass
    return {}


def main():
    results = []
    print(f"[test] 开始 40 轮真实 HTTP 对话测试", flush=True)
    print(f"[test] 服务器: {SERVER}", flush=True)

    for i, user_input in enumerate(INPUTS):
        t0 = time.time()
        reply, error = post_chat(user_input)
        elapsed = time.time() - t0

        mem = read_memory()
        csv_data = get_latest_pain_log()

        climate = mem.get("internal_climate", {})
        self_model = mem.get("self_model", {})

        record = {
            "round": i,
            "phase": "A" if i < 10 else ("B" if i < 20 else ("C" if i < 30 else "D")),
            "user_input": user_input,
            "reply": reply[:200] if reply else "",
            "error": error,
            "internal_pain": self_model.get("internal_pain", 0.0),
            "low_energy_signal": self_model.get("low_energy_signal", 0.0),
            "rigidity_signal": self_model.get("rigidity_signal", 0.0),
            "withdraw_tendency": self_model.get("withdraw_tendency", 0.0),
            "E": climate.get("energy", None),
            "T": climate.get("tension", None),
            "M": climate.get("emotion_intensity", None),
            "total_interactions": mem.get("user_model", {}).get("total_interactions", -1),
            "csv_pain": csv_data.get("csv_pain", ""),
            "csv_low_energy": csv_data.get("low_energy", ""),
            "csv_rigidity": csv_data.get("rigidity", ""),
            "csv_behavior_tier": csv_data.get("behavior_tier", ""),
            "csv_note": csv_data.get("note", ""),
            "elapsed_s": round(elapsed, 2),
        }
        results.append(record)

        pain_flag = "PAIN_OK" if record["internal_pain"] > 0 else "PAIN_ZERO"
        print(
            f"[round {i:02d}] phase={record['phase']} "
            f"pain={record['internal_pain']:.3f} {pain_flag} "
            f"tier={csv_data.get('behavior_tier', '?')} "
            f"E={record['E']:.3f} T={record['T']:.3f} "
            f"reply_len={len(reply) if reply else 0} "
            f"note={csv_data.get('note', '')[:30]}",
            flush=True,
        )

    # 保存结果
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[test] 完成。结果写入: {RESULT_PATH}", flush=True)
    print(f"[test] 总轮数: {len(results)}", flush=True)

    # 汇总
    pains = [r["internal_pain"] for r in results]
    tiers = [r["csv_behavior_tier"] for r in results if r["csv_behavior_tier"]]
    print(f"\n[汇总] pain 范围: [{min(pains):.4f}, {max(pains):.4f}]")
    print(f"[汇总] pain 非零轮数: {sum(1 for p in pains if p > 0)}/{len(pains)}")
    print(f"[汇总] behavior_tier 分布: {dict((t, tiers.count(t)) for t in set(tiers))}")


if __name__ == "__main__":
    main()
