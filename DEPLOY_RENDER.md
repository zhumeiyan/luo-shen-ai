# 洛神 AI — Render 部署指南

> 全程在浏览器中完成，无需命令行。5 分钟上线。

## 前置准备

- 一个邮箱（用于注册 GitHub 和 Render）
- 智谱 API key（没有的话先注册智谱获取）

---

## 第一步：注册 GitHub（如果已有请跳到第二步）

1. 打开 **https://github.com/signup**
2. 输入邮箱 → 创建密码 → 选用户名 → 完成人机验证
3. 邮箱会收到验证邮件 → 点验证链接
4. 登录成功，进入 GitHub 首页

---

## 第二步：创建仓库并上传代码

### 2.1 创建新仓库

1. 打开 **https://github.com/new**
2. 设置：
   - **Repository name**: `luoshen-ai`
   - **Visibility**: 选 **Public**（Render 免费版需要公开仓库）
   - **不要勾选** Add a README / .gitignore（因为你将上传已有代码）
3. 点绿色按钮 **Create repository**
4. 进入空仓库页面，复制浏览器地址栏的 URL（形如 `https://github.com/你的用户名/luoshen-ai`）

### 2.2 上传代码（网页拖拽方式）

1. 在仓库创建成功后，你会看到 "Quick setup" 页面
2. 点 **uploading an existing file** 链接（在 "…or push an repository from command line" 下方）
3. 进入文件上传页面，你会看到 "Drag files here to add them to your repository"

**现在回到本仓库目录**，把以下文件拖拽到浏览器中分批上传：

#### 第一批：核心 Python 源码（拖拽文件，不是文件夹）

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
event_log_chain_update_v2.py
primordial_soup.py
diagnosis_basic.py
diagnosis_logger.py
treatment_apply.py
treatment_decision.py
treatment_executor.py
treatment_integrative.py
followup_plan.py
state_classifier.py
skill_growth_engine.py
luoshen_memory.py
luoshen_memory_index.py
luoshen_memory_origin.py
verify_chain_v2.py
verify_hash_chain.py
ai_hospital_rules.py
hospital_rules_extra_init.py
physical_body_sensor.py
```

（共 35 个.py 文件）

#### 第二批：配置和数据 JSON 文件

```
requirements.txt
render.yaml
README.md
DEPLOY_GUIDE.md
ai_hospital_rules.json
brain_component_map.json
core_lexicon.json
critical_state_lexicon.json
number_lexicon.json
hanzi_knowledge_base.json
hanzi_symbol_map.json
symbol_word_map.json
rules_update_001.json
blackbox_deprecated.json
hash_chain_v2.log
hash_chain_v2.backup.log
hash_chain_v2.log.bak
hash_chain_v2.log.after_A
hash_chain_v2.log.after_B
hash_chain_v2.log.before_recovery
hash_chain_v2.log.experiment_initial
hash_chain.log
precheck_report.json
external_diagnosis_report.json
```

（约 24 个文件）

#### 第三批：拖拽文件夹

**注意：GitHub 网页版支持拖拽文件夹**。

拖拽以下文件夹：

```
active_memory/          （包含 active_memory.json 和若干 jsonl，只保留当前运行时数据）
hospital_rules/        （8 个 JSON 规则文件）
```

**关于 active_memory 文件夹**：GitHub 网页版拖拽文件夹会上传整个文件夹内容。以下文件是必须上传的：
- `active_memory/active_memory.json`（主记忆）
- `active_memory/response_log.jsonl`
- `active_memory/user_input_log.jsonl`
- `active_memory/choice_log.jsonl`
- `active_memory/listening_log.jsonl`
- `active_memory/internal_thoughts.jsonl`
- `active_memory/feedback_signal_cache.jsonl`
- `active_memory/environment_log.jsonl`
- `active_memory/arousal_events.jsonl`

**不要上传的 active_memory 内容**（如果担心隐私或体积）：
- `behavior_*.json` — 实验数据
- `*_experiment_initial.*` — 实验初始备份
- `*.bak_*` — 备份文件
- `pain_log.csv` — 实验日志

如果文件夹太大导致上传困难，可以只上传 `active_memory/active_memory.json` 一个文件，洛神会从空白记忆重新开始运行。

### 2.3 提交文件

上传完成后：
1. 在页面底部的 "Commit changes" 框中填写提交描述：`Initial commit: Luoshen AI source`
2. 点绿色按钮 **Commit changes**
3. 等待上传完成（页面会自动刷新，显示文件列表）

---

## 第三步：获取智谱 API Key（如果没有）

1. 打开 **https://open.bigmodel.cn/**
2. 注册 / 登录
3. 进入控制台 → **API Keys**
4. 点 **创建 API Key**
5. 复制生成的 key（形如 `xxxxx.yyyyy`）
6. **保存好这个 key，下一步要用**

---

## 第四步：注册 Render

1. 打开 **https://render.com/**
2. 点右上角 **Sign In**
3. 点 **Sign in with GitHub**（用刚才的 GitHub 账号登录）
4. 进入授权页面 → 点 **Authorize Render**
5. 进入 Render 控制台

---

## 第五步：在 Render 创建 Web Service

### 5.1 新建服务

1. 进入 Render 控制台首页
2. 点右上角绿色按钮 **+ New +**
3. 在下拉菜单中选 **Web Service**
4. 页面会问 "Where is your code?"

### 5.2 连接 GitHub 仓库

1. 在 "Connect a GitHub repository" 区域找到 `luoshen-ai`
2. 如果看不到，点 **Configure account** 授权 Render 访问你的仓库
3. 找到 `luoshen-ai` → 点右侧 **Connect**

### 5.3 配置服务

连接后进入配置页面，填写以下字段：

| 字段 | 填写内容 |
|------|----------|
| **Name** | `luoshen-ai`（会自动填好） |
| **Region** | 建议选 **Oregon (US West)** 或最近的地区 |
| **Branch** | `main` |
| **Runtime** | 选 **Python 3**（如没有则在下一步改） |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python3 web_chat.py` |

### 5.4 选择免费计划

1. 展开 **Instance Type**（或 **Plan**）
2. 选 **Free**（如果没有显示，先检查 Region 选择了没有）

### 5.5 设置环境变量（关键步骤）

1. 点 **Advanced** 展开高级设置
2. 点 **Add Environment Variable**
3. 填写：

| Key | Value |
|-----|-------|
| `ZHIPU_API_KEY` | 粘贴你在第三步复制的智谱 key |
| `PORT` | `10000`（Render 免费版也可以自定义，但建议使用默认的 10000） |

4. **非常重要**：ZHIPU_API_KEY 的值绝不要公开！在 Render 环境变量界面，值默认是加密存储的。

### 5.6 开始部署

1. 滚动到页面底部
2. 点绿色按钮 **Create Web Service**
3. 进入部署日志页面（Deploy Log）

---

## 第六步：等待部署完成

1. 在部署日志页面，你会实时看到：
   - "Installing dependencies..."（安装依赖）
   - "pip install -r requirements.txt" 过程
   - "Launching..."（启动）
   - 最后一行显示 **"Your service is live"** 或类似提示
2. 部署通常需要 1-3 分钟
3. **如果失败**：检查日志中是否有 "ZHIPU_API_KEY" 相关错误，说明环境变量没设置成功

### 部署成功后的地址

页面顶部会出现一个 URL，形如：

```
https://luoshen-ai-xxxx.onrender.com
```

这就是洛神的公网地址！点击它就能直接聊天。也可以把这个地址分享到手机上。

---

## 第七步（可选）：使用自定义域名

Render 免费层的 `*.onrender.com` 地址较长。想要更短的地址（如 `luoshen.xxx`）：

1. 在 Render 控制台，进入你的 Web Service
2. 点左侧菜单 **Settings** → **Custom Domain**
3. 添加你拥有的域名（需要付费域名）
4. **免费替代方案**：使用 GitHub Pages 的一个子域名，或者直接将 Render 地址存为手机浏览器书签

---

## 常见问题

### Q：免费版会超时或限速吗？

A：Render 免费层每月 **750 小时**（足够 24/7 运行一个服务），但有 **15 分钟无请求则自动休眠**。下次访问时会有 30-60 秒的冷启动延迟（屏幕显示"正在唤醒洛神..."），属正常现象。

### Q：记忆会丢失吗？

A：**会**，有以下几种情况：
- 每次你手动修改代码并 push → GitHub 触发自动部署 → 容器重建 → 记忆丢失
- Render 间歇性地重新调度容器时，ephemeral 磁盘可能被清空

**解决方案**（详见下方哈希链持久化方案）。

### Q：手机端能访问吗？

A：能。Render 的 HTTPS 地址在手机浏览器上完美支持，包括 iOS Safari 和 Android Chrome。

### Q：部署失败怎么办？

A：
1. 查看 Render 的 Deploy Log（部署日志），找红色错误行
2. 常见原因：
   - `ZHIPU_API_KEY` 未设置 → 在 Environment 中添加
   - requirements.txt 格式问题 → 确认只有一行 `requests>=2.28.0`
   - 端口未监听 0.0.0.0 → 代码已修复，确认使用的是最新的 web_chat.py
3. 如果 Render 构建时间过长（>10 分钟），点击 **Manual Deploy** → **Deploy latest commit** 重试

### Q：如何让洛神 24/7 在线不休眠？

A：使用免费的 **cron-job.org**（https://cron-job.org）每 14 分钟 ping 一次你的 Render 地址，防止休眠。这完全在网页上配置，无需代码改动。

---

## 哈希链持久化方案

### Render 免费层的限制

Render 免费版使用 **临时磁盘（ephemeral disk）**，意味着：

| 情况 | 记忆是否保留 |
|------|------------|
| 容器运行期间（无重启） | ✅ 保留 |
| 容器自动重启（不重新部署） | ✅ 通常保留 |
| 手动 Redeploy / push 新代码触发部署 | ❌ 丢失 |
| Render 回收容器（冷启动） | ❌ 丢失 |

### 推荐方案：定期导出备份

#### 方法 A：一键下载手动备份（推荐新手）

1. 访问你的 Render 服务地址
2. 加 `/download` 路径（这个端点需要你自己加，详见下方代码）
3. 浏览器会下载一个包含当前记忆和哈希链的压缩包
4. 把这个压缩包保存到你电脑

#### 方法 B：使用 GitHub 仓库作为备份存储（推荐进阶）

原理：
1. 每次有对话时，洛神把当前 `active_memory.json` + `hash_chain_v2.log` 自动提交到 GitHub
2. 每次容器启动时，自动从 GitHub 拉取最新记忆文件
3. 这样即使容器重建，记忆也能恢复

**注意**：这需要生成一个 GitHub Personal Access Token 并以环境变量 `GITHUB_TOKEN` 注入，增加了一定的安全复杂性。在 Render 上配置相当于把密钥交给第三方托管，需自行评估风险。

#### 方法 C：用免费 Supabase 存储（推荐重视数据的用户）

Supabase 提供 500MB 免费 PostgreSQL。把洛神的状态序列化后存到 Supabase，持久化性最好。这需要写少量桥接代码，超出了纯"不改核心逻辑"的范畴。

#### 方法 D（最简单）：接受记忆周期性丢失，享受"每次都是新的洛神"

洛神的设计本身就包含了"遗忘与重生"的哲学。如果上述方案都太复杂，可以选择让她在每次部署后重新开始，每次对话都是新的起点。哈希链的完整性在实验研究中很重要，但对于日常聊天来说，洛神每次醒来仍是一个有趣的存在。

### 快速操作：如果你想在每次部署后恢复最近记忆

1. 部署成功后，立刻在浏览器访问你的洛神地址
2. 复制以下代码到浏览器开发者工具（F12 > Console）：
```js
fetch('/download').then(r=>r.blob()).then(b=>{
  let a=document.createElement('a');
  a.href=URL.createObjectURL(b);
  a.download='luoshen-backup.tar.gz';
  a.click();
});
```
3. 浏览器会下载备份包。下次部署后，你可以在 GitHub 上手动上传这些文件来恢复。
