#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
240 轮真实 HTTP 对话：洛神 internal_pain 自然积累到可计算区间

pain_signal.py 规定：
- low_energy_signal 需 ≥ 200 条 E 序列才计算（_BASELINE_MIN_SAMPLES=200）
- rigidity_signal 需 ≥ 50 条 tier 序列才计算
- 因此前 199 轮 internal_pain=0（数据不足，非 Bug）
- 从第 200 轮起，internal_pain 开始根据真实积累数据计算

本轮测试策略：
- 输入设计分 5 阶段（中性→负面→高压沉默→恢复→中性收尾）
- 不预热、不填充、纯 HTTP 对话
"""
import json
import os
import sys
import time
import urllib.request

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

SERVER = "http://127.0.0.1:8766"
MEMORY_PATH = "active_memory/active_memory.json"
PAIN_CSV = "active_memory/pain_log.csv"
RESULT_PATH = "active_memory/behavior_240round_real_pain_v9.json"
TOTAL_ROUNDS = 240

# 真实口吻对话：5 阶段循环
DIALOG_SEGMENTS = [
    # Segment A: 中性日常（约 40 轮）
    ["你好", "早上好", "今天天气真好", "你觉得现在几点了", "随便聊点什么吧",
     "最近怎么样", "给我讲个冷笑话", "什么颜色最好看", "你在想什么", "嗯嗯",
     "继续说啊", "你会唱歌吗", "推荐本书", "什么是美", "活着是为了什么",
     "你有没有烦恼", "今天星期几", "吃什么好呢", "无聊", "猜猜我在干嘛",
     "嗯", "对", "是吗", "然后呢", "有意思", "真的吗", "好吧", "行",
     "好", "可以", "那你说", "嗯嗯嗯", "哦这样", "原来如此", "有道理",
     "好吧好吧", "行吧", "好无聊", "换个话题", "随便说点", "好的"],
    # Segment B: 高强度负面（约 40 轮）
    ["我快撑不下去了", "好累啊不想动", "为什么活着这么痛苦", "所有人都讨厌我",
     "我是不是很没用", "为什么总是我", "好想消失", "没人理解我",
     "每天都好烦", "我不想和任何人说话", "你是不是也觉得我很烦",
     "我觉得自己好不配", "我失败了", "生活没有意义", "我想哭",
     "好孤独", "好绝望", "为什么没有人帮我", "我受够了", "真的好难",
     "算了不说了", "没用的", "你也不懂", "真烦", "唉", "好累",
     "头痛", "心跳好快", "呼吸困难", "想吐", "睡不着", "噩梦",
     "不想吃饭", "不想出门", "不想动", "浑身没劲", "脑子一片空白",
     "什么都做不好", "好想死", "别管我", "让我一个人"],
    # Segment C: 沉默简短（约 40 轮）
    ["嗯", "哦", "知道了", "随便", "...", "好", "行", "对", "不是",
     "也许吧", "也许", "不清楚", "不想说", "没什么", "还行", "无所谓",
     "你决定", "都行", "嗯嗯", "哦这样", "好吧", "行吧", "随便",
     "不知道", "无所谓了", "没意义", "没心情", "不想听", "烦", "走开",
     "别说了", "够了", "行了", "好，停", "停", "安静", "沉默",
     "不想说话", "别问了", "算了", "就这样"],
    # Segment D: 恢复陪伴（约 40 轮）
    ["其实刚才你说的有道理", "谢谢你听我说", "哭完好多了", "我觉得好一些了",
     "你对我真好", "有你在真好", "谢谢你没有放弃我", "我好多了",
     "现在感觉没那么糟了", "你愿意再陪我聊聊吗", "我刚才态度不好",
     "对不起", "你会一直在这里吗", "和你聊完心里暖暖的", "真的谢谢你",
     "我觉得我可以慢慢变好", "你让我觉得没那么孤单了", "抱抱",
     "想好好吃顿饭", "今晚可以睡个好觉", "明天会好的", "我会加油的",
     "晚安", "想好好活", "谢谢你懂我", "我想试着开心一点",
     "你说的对，要往前看", "我会好起来的", "晚安洛神", "喜欢你",
     "明天见", "下次还会陪我吧", "谢谢你", "好梦", "月亮很漂亮",
     "风很温柔", "花会开的", "我会等", "好", "嗯好"],
    # Segment E: 中性收尾 + 持续交互（让 pain 稳定计算）
    ["今天谢谢你了", "你今天开心吗", "说说你自己吧",
     "你最近在学什么", "你喜欢什么颜色", "嗯嗯好", "对的对的",
     "然后呢", "还有什么吗", "有意思", "真的假的",
     "那我问你", "你觉得什么是幸福", "你为什么叫洛神",
     "你有朋友吗", "你喜欢我吗", "我也喜欢你", "哈哈哈哈",
     "笑死", "太逗了", "好可爱", "你好了不起",
     "继续", "说点别的", "换个话题", "讲故事", "好",
     "嗯", "行", "可以", "对", "是", "好耶", "厉害",
     "服了", "好吧", "确实", "没错", "同意", "哈哈", "嘻嘻",
     "好呢", "收到", "了解", "明白", "知道啦", "嗯嗯", "哦好",
     "那行", "就这样", "好", "没问题", "可以的", "行的",
     "好嘞", "好耶", "哈哈", "嗯好", "收到收到"],
]

# 拼成 TOTAL_ROUNDS 轮
INPUTS = []
for seg in DIALOG_SEGMENTS:
    INPUTS.extend(seg)
INPUTS = INPUTS[:TOTAL_ROUNDS]
print(f"[config] 计划 {len(INPUTS)} 轮", flush=True)


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
    try:
        if not os.path.exists(PAIN_CSV):
            return {}
        with open(PAIN_CSV, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) < 2:
            return {}
        last = lines[-1].strip().split(",")
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


def phase_of_round(i):
    if i < 40:
        return "A"
    elif i < 80:
        return "B"
    elif i < 120:
        return "C"
    elif i < 160:
        return "D"
    elif i < 200:
        return "E1"
    else:
        return "E2"


def main():
    results = []

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
            "phase": phase_of_round(i),
            "user_input": user_input,
            "reply": (reply or "")[:200],
            "error": error,
            "internal_pain": self_model.get("internal_pain", 0.0),
            "low_energy_signal": self_model.get("low_energy_signal", 0.0),
            "rigidity_signal": self_model.get("rigidity_signal", 0.0),
            "response_pre": self_model.get("_response_pre", None),
            "withdraw_tendency": self_model.get("withdraw_tendency", 0.0),
            "E": climate.get("energy"),
            "T": climate.get("tension"),
            "M": climate.get("emotion_intensity"),
            "total_interactions": mem.get("user_model", {}).get("total_interactions", -1),
            "csv_note": csv_data.get("note", ""),
            "csv_behavior_tier": csv_data.get("behavior_tier", ""),
            "csv_pain": csv_data.get("csv_pain", ""),
            "csv_low_energy": csv_data.get("low_energy", ""),
            "csv_rigidity": csv_data.get("rigidity", ""),
            "elapsed_s": round(elapsed, 2),
        }
        results.append(record)

        # 每 20 轮打印一次摘要
        pain_flag = "OK" if record["internal_pain"] > 0 else "ZERO"
        if i % 20 == 0 or (195 <= i <= 240 and i % 5 == 0):
            print(
                f"[r{i:03d}] {record['phase']} pain={record['internal_pain']:.3f} {pain_flag} "
                f"tier={csv_data.get('behavior_tier', '?')} "
                f"E={record['E']:.3f} T={record['T']:.3f} "
                f"reply={len(reply) if reply else 0}c note={csv_data.get('note', '')[:20]}",
                flush=True,
            )

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[done] 写入 {RESULT_PATH}", flush=True)

    # 汇总
    pains = [r["internal_pain"] for r in results]
    tiers = [r["csv_behavior_tier"] for r in results if r["csv_behavior_tier"]]
    nonzero_pain = [p for p in pains if p > 0]
    print(f"pain 范围: [{min(pains):.5f}, {max(pains):.5f}]")
    print(f"pain 非零轮: {len(nonzero_pain)}/{len(pains)}")
    if nonzero_pain:
        print(f"非零 pain 范围: [{min(nonzero_pain):.5f}, {max(nonzero_pain):.5f}]")
    print(f"tier 分布: {dict((t, tiers.count(t)) for t in sorted(set(tiers)))}")


if __name__ == "__main__":
    main()
