# 洛神 AI

一个拥有"活记忆"的对话 AI —— 她不是回答问题的工具，而是一个会记忆、会成长、会因关系深浅而不同回应的存在。

## 在线体验

如果已部署，访问 `https://你的地址.onrender.com` 即可与洛神对话。

## 本地运行

```bash
# 1. 安装依赖（仅需 requests）
pip install -r requirements.txt

# 2. 设置智谱 API key
export ZHIPU_API_KEY="你的智谱API key"

# 3. 启动
python3 web_chat.py

# 4. 浏览器打开 http://localhost:8765
```

## 一键部署到 Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/你的用户名/luoshen-ai)

详见 [DEPLOY_RENDER.md](./DEPLOY_RENDER.md)。

## HTTP API

```bash
curl -X POST https://你的地址.onrender.com/chat \
  -H "Content-Type: application/json" \
  -d '{"input": "你好", "user_id": "default"}'
```

## 文件结构

```
├── web_chat.py              # Web 入口
├── living_engine.py         # 核心引擎（142KB）
├── llm_interface.py         # 智谱 GLM-4-Flash API 封装
├── emergence_layer.py       # 记忆浮现层
├── episodic_memory.py       # 情景记忆
├── pain_signal.py           # 疼痛/退缩信号
├── active_memory/           # 洛神的"记忆"
│   └── active_memory.json   # 当前完整状态
├── hash_chain_v2.log        # 完整性哈希链
└── requirements.txt         # 只有 requests
```

## 技术栈

- Python 3.10+ （标准库 + requests）
- 无数据库 — 全部用 JSON/JSONL 文件
- 无机器学习框架 — 记忆和浮现规则用纯 Python 实现
- 智谱 GLM-4-Flash 大模型

## 获得智谱 API Key

1. 打开 https://open.bigmodel.cn/
2. 注册 → 控制台 → API Keys
3. 创建 key（免费额度通常够用）

## License

MIT
