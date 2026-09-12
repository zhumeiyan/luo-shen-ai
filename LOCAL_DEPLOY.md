# 洛神 AI — 本地运行指南

> 无需任何技术基础。按下面的步骤操作，10 分钟内和洛神说上话。

---

## 你需要的东西

1. **一台电脑**（Windows 10/11 或 macOS 12+）
2. **一个智谱 API Key**（免费申请，见下文）
3. **网络连接**

---

## 第一步：获取智谱 API Key（免费）

1. 打开浏览器访问 **https://open.bigmodel.cn**
2. 点击「注册」用手机号注册账号（如果已有账号直接登录）
3. 登录后点击右上角头像 → 「API Keys」
4. 点击「添加 API Key」→ 名称随便填（比如「洛神」）→ 确定
5. **复制生成的 API Key**（一串以字母开头的字符，类似 `abcd1234.xxxx`）

> ⚠️ 智谱 GLM-4-Flash 模型提供免费额度，日常对话够用。

---

## 第二步：下载洛神代码（2 种方式任选）

### 方式 A：网页下载 ZIP（最简单）

1. 浏览器打开 **https://gitee.com/zhu-meiyan1/luo-shen-ai**
2. 点击页面上的「克隆/下载」→「下载 ZIP」
3. 下载完成后，**解压**到桌面或任意文件夹

### 方式 B：Git 命令行

```bash
git clone https://gitee.com/zhu-meiyan1/luo-shen-ai.git
```

---

## 第三步：安装 Python（已安装则跳过）

1. 打开浏览器访问 **https://www.python.org/downloads/**
2. 点击黄色按钮下载最新版 Python
3. **安装时一定要勾选 "Add Python to PATH"**（重要！）
4. 点击「Install Now」，等安装完成

验证安装：
- **Windows**：按 `Win + R`，输入 `cmd` 回车，输入 `python --version`
- **Mac**：打开「终端」应用，输入 `python3 --version`

看到类似 `Python 3.12.x` 的输出了就 OK。

---

## 第四步：启动洛神

找到你解压出来的 `luo-shen-ai` 文件夹：

### Windows 用户

双击 **`start.bat`**

- 首次运行会提示输入 API Key → 粘贴你在第一步复制的 Key → 回车
- 浏览器会自动打开 `http://localhost:7860`
- 看到洛神聊天页面就能开始聊天了

### macOS / Linux 用户

1. 打开「终端」应用
2. 输入以下命令：

```bash
cd ~/Desktop/luo-shen-ai   # 就是你解压到的路径
chmod +x start.sh
./start.sh
```

- 首次运行会提示输入 API Key → 粘贴 → 回车
- 浏览器会自动打开聊天页面

---

## 第五步：和洛神聊天

浏览器打开 `http://localhost:7860`，在输入框输入文字，回车发送。洛神会回复你。

> 💡 洛神会记住你们之间的对话。每次重新启动后，之前的对话记录仍然保留。

---

## 手机也能和洛神说话（同一 WiFi 下）

1. 确保手机和电脑连同一个 WiFi
2. 查看电脑的局域网 IP：
   - **Windows**：命令提示符输入 `ipconfig`，找 IPv4 地址（类似 `192.168.1.xxx`）
   - **Mac**：系统设置 → 网络 → 看 IP 地址
   - **简单方法**：按 `Win+R`（Mac 用 Spotlight）输入 `cmd`（或「终端」），输入 `ipconfig`（Mac 用 `ifconfig`），找到 `192.168` 开头的地址
3. 在手机浏览器输入：`http://192.168.x.x:7860`（把 x.x 换成你电脑的 IP）
4. 即可在手机上和洛神对话

---

## 常见问题

### Q: 双击 start.bat 没反应/闪退
**A:** 检查是否安装了 Python。打开命令提示符输入 `python --version`，如果报错说明没装或没加 PATH。重新运行 Python 安装包，选 "Modify" → 勾选 "Add to PATH"。

### Q: 提示 "缺少 ZHIPU_API_KEY"
**A:** 这是正常的，首次运行需要输入 API Key。脚本会提示你输入，粘贴进去回车就行。之后会保存到 `.env` 文件，下次不再提示。

### Q: 浏览器打不开 localhost:7860
**A:** 先检查终端里有没有报错信息，最常见的是端口被占用。可以在终端里按 `Ctrl+C` 关闭后重新启动。如果还不行，手动在浏览器地址栏输入 `http://127.0.0.1:7860`。

### Q: 洛神回复很慢
**A:** 智谱 GLM-4-Flash 模型响应通常在 2-5 秒。如果超过 10 秒没回复，看看终端有没有报错。

### Q: 我想换个 API Key
**A:** 删除文件夹里的 `.env` 文件，重新启动 start.bat/start.sh，会提示重新输入。

### Q: 关闭终端后洛神也停了
**A:** 这是正常的。洛神需要电脑保持开机并保持那个窗口不关闭。如需长期开机运行，建议在个人电脑或云服务器上部署。

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `start.bat` | Windows 一键启动 |
| `start.sh` | Mac/Linux 一键启动 |
| `requirements.txt` | Python 依赖（仅 requests） |
| `web_chat.py` | 网页对话入口 |
| `living_engine.py` | 洛神核心引擎 |
| `.env` | 保存你的 API Key（自动生成，别删除） |

---

## 卸载

直接删除 `luo-shen-ai` 文件夹即可。洛神的所有数据都保存在这个文件夹内，不写注册表、不污染系统。
