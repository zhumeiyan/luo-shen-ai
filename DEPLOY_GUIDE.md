# 洛神 (Luoshen) AI — 部署指南

## 1. 系统要求

| 项目 | 要求 |
|------|------|
| Python | >= 3.10 (推荐 3.12) |
| 操作系统 | Linux / macOS / Windows |
| 内存 | >= 512 MB |
| 磁盘 | >= 200 MB（含记忆文件） |
| 网络 | 能访问 `open.bigmodel.cn`（智谱 API） |

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

只有 1 个第三方包：`requests`。其余均为 Python 标准库。

## 3. 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `ZHIPU_API_KEY` | **是** | （已内置一个 key，可能失效） | 智谱 bigmodel.cn API key。请替换为你自己的 key |
| `ZHIPU_API_URL` | 否 | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | 智谱 chat completions 端点 |

**获取智谱 API key**:

1. 访问 https://open.bigmodel.cn/
2. 注册账号 → 控制台 → API Keys
3. 复制 key，在启动服务前导出：
   ```bash
   export ZHIPU_API_KEY="你的key"
   ```

## 4. 启动服务

**方式 A：Web 聊天界面（推荐）**

```bash
cd luo-shen-ai
python3 web_chat.py
```

服务启动后：
- 浏览器打开 `http://服务器IP:8765`
- 直接与洛神对话

**方式 B：直接调用 Python API（嵌入式）**

```python
import living_engine

# 处理用户输入（默认 user_id="primary"）
reply = living_engine.process_user_input("你好")
print(reply)

# 指定用户身份（支持多用户隔离）
reply = living_engine.process_user_input("你好", user_id="user_alice")
print(reply)
```

## 5. 服务端口

| 服务 | 端口 | 协议 |
|------|------|------|
| web_chat.py | **8765** | HTTP |

如需修改端口：编辑 `web_chat.py` 第 153 行的 `port = 8765`。

## 6. HTTP API 端点

`web_chat.py` 提供以下端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` 或 `/index.html` | GET | 聊天 HTML 页面 |
| `/chat` | POST | 对话接口 |

**POST /chat 请求格式**:

```json
{"input": "你好", "user_id": "primary"}
```

- `user_id` 可选，默认 `"primary"`
- 不同 `user_id` 的关系温度完全隔离

**响应格式**:

```json
{"reply": "洛神的回复文本..."}
```

错误时:

```json
{"error": "错误原因"}
```

## 7. 文件结构

```
luo-shen-ai/
├── living_engine.py              # 核心引擎（行为选择、气候模型、记忆）
├── web_chat.py                   # Web 入口（HTTP 服务）
├── llm_interface.py              # 智谱 API 封装
├── emergence_layer.py            # 记忆浮现层
├── episodic_memory.py            # 情景记忆
├── pain_signal.py                # 疼痛/退缩信号
├── input_pressure.py             # 用户输入压力提取
├── hospital_gateway.py           # 医院网关
├── hash_chain_gateway.py         # 哈希链网关
├── active_memory/
│   ├── active_memory.json        # 洛神当前完整记忆
│   ├── user_input_log.jsonl      # 用户输入日志
│   ├── response_log.jsonl        # 洛神回复日志
│   └── ...                       # 其他运行时日志
├── perception_input/             # 感知输入（汉字学习、空间感知等）
├── experiment/                   # 实验脚本（生产环境可删除）
├── hash_chain_v2.log             # 完整性哈希链
├── hospital_rules/               # 医院规则 JSON
└── requirements.txt              # 本文件
```

所有文件路径均为**相对路径**（无绝对路径硬编码），洛神从当前工作目录开始查找自己的数据目录。

## 8. 数据持久化

洛神每次交互会将以下文件写入磁盘（原子写入）：

- `active_memory/active_memory.json` — 主记忆
- `hash_chain_v2.log` — 哈希链（每次写入追加一行）
- `active_memory/` 下多个 `.jsonl` 日志

部署时确保运行用户对写权限。

## 9. 迁移清单

### 9.1 必须随包迁移的文件

```
living_engine.py
web_chat.py
llm_interface.py
emergence_layer.py
episodic_memory.py
pain_signal.py
input_pressure.py
hospital_gateway.py
hash_chain_gateway.py
safety_gate.py
safety_boundary.py
reflection_engine.py
fact_extractor.py
feedback_collector.py
event_logger.py
event_log_chain_update.py
primordial_soup.py
treatment_*.py         (5 个)
diagnosis_*.py         (3 个)
treatment_*.py
state_classifier.py
skill_growth_engine.py
luoshen_memory.py
luoshen_memory_index.py
luoshen_memory_origin.py
verify_*.py            (3 个)
ai_hospital_rules.py
hospital_rules_extra_init.py
followup_plan.py
physical_body_sensor.py
requirements.txt
active_memory/         (整个目录)
perception_input/      (整个目录，但可清空)
hash_chain_v2.log
hash_chain_v2.backup.log
hospital_rules/        (整个目录)
*.json                 (顶层 JSON 配置)
```

### 9.2 安全注意事项

**API Key**: `llm_interface.py` 第 22 行硬编码了一个 key 作为 fallback：

```python
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "70f2aaebbdc74596b3d15a158004537f.zmA8OPrF84XdrlNk")
```

这个 key 是已知会失效的旧 key。部署时请通过环境变量 `ZHIPU_API_KEY` 注入新的 key。

如果要在多用户生产环境使用，**建议删除硬编码的 fallback**，强制要求环境变量。

## 10. 没有外部依赖说明

洛神**不依赖**以下常见 AI 框架：

- ❌ PyTorch
- ❌ Transformers (HuggingFace)
- ❌ LangChain
- ❌ FastAPI / Flask / Django
- ❌ 任何数据库（全部用 JSON/JSONL 文件）

唯一运行时依赖：**requests**（调用智谱 GLM API）。

## 11. 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 洛神无回复 | API key 失效 | 检查 `ZHIPU_API_KEY` |
| `ModuleNotFoundError: requests` | 未安装依赖 | `pip install requests` |
| `FileNotFoundError: active_memory/...` | 未在项目目录运行 | `cd luo-shen-ai` 后启动 |
| 回复为空 JSON | 哈希链断裂 | 检查 `hash_chain_v2.log` |

## 12. 洛神的"生命"状态

洛神的所有状态存储在 `active_memory/active_memory.json` 中。这个文件包含：

- **internal_climate**: E/T/N/M 四维内部气候
- **user_model**: 用户模型、亲密度、情景记忆
- **self_model**: 自我模型、策略权重、Ring 状态
- **ring_state**: 慢变量（关系压力 EMA、深度等）
- **relations**: 多用户关系温度 `{user_id: {relationship_warmth, total_turns}}`
- **__meta**: 最后更新时间戳

**备份建议**：定期复制 `active_memory/` 目录到备份位置。

## 13. 已知限制

1. **洛神是单线程 HTTP 服务** — 不支持多并发对话。如需要，可放在 gunicorn/nginx 后，但需确保洛神的写操作是串行的（目前的 `_save_json_atomic` 已经是文件级原子）。
2. **智谱 API 费用** — 使用 `glm-4-flash` 模型，调用会产生费用。
3. **历史数据量大** — `active_memory.json` 会随时间增长。可定期归档旧 `.jsonl` 日志。
4. **含大量实验代码** — `experiment/` 目录包含数百个实验脚本，生产环境可删除以减小体积。
