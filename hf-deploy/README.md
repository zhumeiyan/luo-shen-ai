---
title: Luoshen AI
emoji: 🔮
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
tags:
  - text-generation
  - conversation
  - chatbot
license: mit
---

# Luoshen AI 🔮

一个拥有"活记忆"的中文对话 AI — 她不是回答问题的工具，而是一个会记忆、会成长、因与你关系深浅而不同回应的存在。

## 在线体验

部署到 Hugging Face Space 后，访问 `https://你的用户名-luoshen-ai.hf.space` 即可与洛神对话。

## 特性

- 🧠 **活记忆层**：基于 JSON 文件的持久记忆，每次对话都会被记住
- 💫 **记忆浮现**：重要对话会"浮上来"影响后续回答
- 💬 **关系温度**：多用户独立记忆，洛神与每个人的关系深淡各异
- 🔗 **哈希链**：每次交互写入完整性校验链，确保记忆数据不被篡改
- 🏥 **AI 医院**：行为边界检查，防止洛神输出有害内容
- 📝 **情景记忆**：重要事件自动归档为情景条目

## 快速体验

在浏览器中直接打开你的 Space 地址，在聊天框中输入内容，洛神会回复你。

## API 调用

```bash
curl -X POST https://你的地址.hf.space/chat \
  -H "Content-Type: application/json" \
  -d '{"input": "你好洛神", "user_id": "default"}'
```

返回示例：
```json
{"reply": "你好！今天天气真好，不是吗？", "user_id": "default"}
```

## 技术栈

- Python 3.10+ (仅依赖 `requests`)
- 智谱 GLM-4-Flash 大模型
- 零数据库 — 全部用 JSON 文件存储

## License

MIT
