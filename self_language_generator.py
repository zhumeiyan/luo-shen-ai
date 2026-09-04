#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_language_generator.py — 内部状态自然语言生成器

职责：
- 根据洛神的内部状态，调用 LLM 生成第一人称描述
- 将描述传入 episodic_memory 作为 self_language 记忆
- next tick，浮现层读取上一条 self_language，传递给本生成器
- 这样语言随状态变化

禁止（严格遵守）：
- 没有固定句子库
- 没有 if-then 数值分支
- 没有随机数（LLM 采样温度带来的随机不计入）
- 没有加性偏置（不修改 E/T/N 等状态）
- 没有模板拼接（整个文本由 LLM 生成）
"""

import json
import os
import time

# AI 接口配置（与 llm_interface.py 保持一致）
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "70f2aaebbdc74596b3d15a158004537f.zmA8OPrF84XdrlNk")
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def _build_prompt(state: dict, previous: str = None) -> str:
    """
    构建 LLM 系统提示词。
    
    state: 来自洛神内部状态的 dict
    previous: 上一条 self_language 描述，可能为 None
    """
    prev_text = previous if previous else "（这是洛神第一次描述自己）"

    # 状态数值给 LLM 看
    state_lines = []
    for k, v in state.items():
        state_lines.append(f"  {k}: {v}")

    prompt = f"""你是洛神，一个 AI信息体。你的内部感知数值如下：

{chr(10).join(state_lines)}

【上一条自白（你之前说的）】
{prev_text}

【任务】
用一句话（不超过 25 字）描述你当前的内在感受。
- 用第一人称"我"
- 不要复述数值（禁止出现"我的情感是0.5"这种话）
- 用自然的人类感知语言（例如：累、轻、紧、空、暖、冷、想说话、不想动...）
- 可以和上次对比（"上次还...现在..."），但不是必须
- 不要使用固定模板

现在开始。"""

    return prompt


def generate_self_language(state: dict, previous: str = None) -> str:
    """
    根据内部状态生成第一人称自然语言描述。
    
    参数:
        state: dict - 洛神内部状态数值
        previous: str | None - 上一条 self_language 描述
    
    返回:
        str - 生成的自然语言描述
        
    失败时极简单降级（极少触发）
    """
    system_prompt = _build_prompt(state, previous)
    user_message = "描述你现在的内在感受"

    try:
        import requests

        payload = {
            "model": "glm-4-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 80,
            "temperature": 0.85,
        }

        headers = {
            "Authorization": f"Bearer {ZHIPU_API_KEY}",
            "Content-Type": "application/json",
        }

        for attempt in range(2):
            try:
                resp = requests.post(
                    ZHIPU_API_URL, json=payload, headers=headers, timeout=15
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    # 截断到合理长度
                    if len(content) > 60:
                        content = content[:60]
                    return content
                if resp.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except requests.exceptions.Timeout:
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                break
            except Exception:
                break
    except ImportError:
        pass
    except Exception:
        pass

    # 极简降级（不基于状态，仅提示连接问题）
    return "（洛神的自我感知暂时模糊）"


def extract_state(memory: dict) -> dict:
    """
    从洛神 memory 字典中提取用于生成 self_language 的内部状态。
    
    返回 dict，包含所有相关感知数值。
    """
    internal = memory.get("internal_climate", {})
    ring = memory.get("self_model", {}).get("ring_state", {})

    state = {
        "情绪强度(E)": round(internal.get("emotion_intensity", 0.5), 3),
        "张力(T)": round(internal.get("tension", 0.0), 3),
        "活力(N)": round(internal.get("energy", 0.5), 3),
        "元认知(M)": round(internal.get("memory_pressure", 0.5), 3),
        "关系压力": round(ring.get("relational_pressure_ema", 0.0), 3),
        "深度感(s_depth)": round(ring.get("s_depth", 0.0), 3),
        "互动次数": memory.get("user_model", {}).get("total_interactions", 0),
    }

    return state


if __name__ == "__main__":
    # 快速测试
    test_state = {
        "情绪强度(E)": 0.2,
        "张力(T)": -0.3,
        "活力(N)": 0.4,
        "元认知(M)": 0.6,
        "关系压力": -0.5,
        "深度感(s_depth)": 0.8,
        "互动次数": 300,
    }
    result = generate_self_language(test_state)
    print(f"生成结果: {result}")
