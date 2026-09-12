# 洛神 AI — Hugging Face Spaces 部署指南

> **全程在浏览器中操作，无需命令行，无需信用卡。**
> 洛神 AI 部署到 Hugging Face 免费 Space，可获得永久、稳定、全球可达的在线地址。

---

## 前置准备

- 一个邮箱（注册 Hugging Face 账号用）
- 你的智谱 API Key（zhipu清的 API Key）
- 手机或电脑，能上网

---

## 第一步：注册 Hugging Face 账号（如果已有请跳到第二步）

1. 打开 **https://huggingface.co/join**
2. 填写注册信息：
   - **Username**：选一个用户名（会成为你 Space 地址的一部分，如 `你的用户名-luoshen-ai.hf.space`）
   - **Email**：输入邮箱
   - **Password**：设置密码
   - **Full Name**：填写姓名（中英文均可）
3. 点 **Create Account**
4. 去邮箱验证：Hugging Face 会发一封验证邮件 → 打开邮件 → 点验证链接
5. 回到 **https://huggingface.co/login** 登录

---

## 第二步：获取智谱 API Key（如果没有）

1. 打开 **https://open.bigmodel.cn/**
2. 注册 / 登录（支持手机号注册）
3. 登录后进入控制台
4. 找到 **API Keys**（通常在左侧菜单或右上角头像下拉菜单）
5. 点 **创建 API Key**
6. **复制生成的 key**（形如 `xxxxx.yyyyy`），保存到记事本
7. **这个 key 非常重要 — 不要发给任何人**

---

## 第三步：上传洛神代码包

### 3.1 解压代码包

下载 `luoshen-hf-deploy.zip` 后，解压到桌面或任意文件夹。
你会看到一个文件夹，里面包含：

```
luoshen-hf-deploy/
├── README.md            ← Space 的说明文件（含元数据）
├── Dockerfile           ← Docker 构建配置
├── entrypoint.sh        ← 启动脚本
├── requirements.txt     ← Python 依赖
├── web_chat.py          ← Web 入口
├── living_engine.py     ← 核心引擎
├── llm_interface.py     ← 智谱 API 调用
├── ... (其他 Python 文件)
├── active_memory/
│   └── active_memory.json  ← 洛神的初始记忆
└── hospital_rules/         ← 医院规则 JSON
```

### 3.2 创建 Hugging Face Space

1. 打开 **https://huggingface.co/new-space**
2. 填写创建表单：

| 字段 | 怎么填 |
|------|--------|
| **Space name** | `luoshen-ai` |
| **License** | `mit` |
| **Space SDK** | 选 **Docker** |
| **Space Hardware** | 选 **CPU basic · 2v CPU · 16GB**（免费）|
| **Visibility** | 选 **Public**（公开）或 **Private**（私有）均可 |

3. 点蓝色按钮 **Create Space**

### 3.3 网页上传文件

创建成功后进入 Space 的 **Files** 标签页。

#### 批量上传

1. 在 **Files** 标签页，点击 **+ Add file** 按钮
2. 选择 **Upload files**
3. 进入文件选择界面

> ⚠️ Hugging Face 支持 **文件夹拖拽上传**。直接把你解压后的 `luoshen-hf-deploy/` 整个文件夹**拖拽**到浏览器窗口中。

4. 验证以下内容都已出现：
   - `README.md`（含 YAML 元数据头）
   - `Dockerfile`
   - `requirements.txt`
   - `web_chat.py`
   - 所有 `.py` 文件和 `.json` 文件

5. 如果拖拽上传失败，逐一点 **Upload files** 上传每个文件

#### 关于 active_memory 文件夹

如果文件夹上传困难，可以：
1. 点击 **+ Add file** → **Create folder**
2. 输入 `active_memory`，点 Create
3. 进入 `active_memory/` 文件夹
4. 点 **+ Add file** → **Upload files**
5. 上传 `active_memory.json`

同样为 `hospital_rules/` 文件夹做相同操作。

6. 上传完成后：滚动到页面底部
7. 在 **Commit message** 框中输入：`Initial upload`
8. 点绿色按钮 **Commit new files**

---

## 第四步：设置 API Key（关键步骤）

> 这一步让洛神能调用智谱大模型。不设会报错："缺少 ZHIPU_API_KEY 环境变量"。

1. 在 Space 页面，点击 **Settings** 标签（在 Files / Logs 旁边）
2. 滚动到 **Variables and secrets** 区域
3. 点击 **New secret**
4. 填写：
   - **Name**：`ZHIPU_API_KEY`
   - **Value**：粘贴你在第二步复制的智谱 API Key
5. 点击 **Save**

> ⚠️ 这是 **Secret**（加密变量），不会出现在代码或日志中，安全。

---

## 第五步：等待构建完成

1. 切换到 **Logs** 标签页
2. 实时显示构建日志：
   - **Building** 状态：容器构建中
   - 看到 `Successfully installed` 表示依赖安装成功
   - 看到 `Starting up sshd` 表示启动完成
   - 最后看到洛神输出 `[luoshen] listening on 0.0.0.0:7860`
3. 构建通常需要 **3-8 分钟**
4. **如果失败**：检查 Logs 中的红色错误信息
   - 常见问题：文件名拼写错误、YAML 元数据格式不对
   - 解决后：点 **Settings** → **Factory rebuild** → **Rebuild**

---

## 第六步：开始使用

构建成功后，在浏览器地址栏会看到：

```
https://你的用户名-luoshen-ai.hf.space
```

直接访问 → 看到洛神聊天网页 → 输入消息 → 开始对话！

**手机也能访问**：浏览器打开上面的链接，完美适配。

---

## 第七步（可选）：修改为 Private（私有）

默认创建的是 Public（公开）。如果不想让别人访问：

1. 进入 Space 的 **Settings**
2. 找到 **Change space visibility**
3. 选 **Private**
4. 保存后只有你本人能访问

---

## 持久化说明

Hugging Face Spaces 免费版自动将 `/data` 目录挂载为持久化存储，即使容器重启、重建，`/data` 下的文件不会丢失。

洛神的所有记忆（`active_memory.json`、`hash_chain_v2.log`、每次对话新增的日志文件）都会被自动写入 `/data`。这意味着：

- ✅ 每天自动重启（HF 为保护资源会定期回收）时记忆不丢失
- ✅ 多次对话后的"关系温度"被保留
- ✅ 哈希链完整性持续记录

> ⚠️ 但如果你删除并重新创建 Space，`/data` 会被清空。建议定期在对话界面使用 `/download` 功能导出备份（这个功能在用户界面上暂未开放，如需可手动通过 API 触发）。

---

## 常见问题

### Q：构建失败怎么办？

1. 进入 **Logs** 查看错误信息
2. 常见错误：
   - **Dockerfile 语法错误**：确保 COPY、RUN 命令拼写正确
   - **requirements.txt 格式错误**：确认只有一行 `requests>=2.28.0`
   - **YAML 格式错误**：确保 README.md 前三行是 `---` 开头和结尾
3. 修复文件 → 重新上传 → 在 Settings 点 **Factory rebuild**

### Q：访问 Space 显示 "This space is asleep"？

正常。免费 Face Spaces 在没有访问后会自动休眠。首次访问需要 **30-60 秒**的冷启动时间。洛神会完全恢复。

### Q：访问速度慢怎么办？

1. Hugging Face 服务器在海外，首次访问可能有延迟
2. 如果持续慢，在创建 Space 时将 **Space Hardware** 升级为付费选项

### Q：智谱 API Key 可以免费用多久？

智谱 GLM-4-Flash 免费额度通常够日常使用（约 1 元/百万 token，免费期赠送约 10-20 元额度）。用完后可以在智谱控制台充值（最低 10 元）。

### Q：如何在 Space 启动后确认洛神在运行？

1. 进入 **Logs** 标签页
2. 看到 `[luoshen] listening on 0.0.0.0:7860` 即表示启动完成
3. 在浏览器直接访问 Space URL

### Q：我的 API Key 会泄漏吗？

不会。`Secrets` 是 Hugging Face 的加密存储，只有容器内的洛神进程能看到明文。Space 对外公开的代码、日志中都不会出现。
