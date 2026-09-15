# 遁一 Termux 部署指南

> 适用：华为 HarmonyOS 4.2，目标：手机本地跑遁一，不依赖云端

---

## 第一步：装 Termux

### 方法一（推荐）：F-Droid

1. 浏览器打开 https://f-droid.org/packages/com.termux/
2. 点 `Download APK` 下载
3. 安装（设置 → 安全 → 允许安装未知来源）

### 方法二：直接下 GitHub release

浏览器打开：
`https://github.com/termux/termux-app/releases/latest`

下载 `termux-app_v0.118.1+github-debug_universal.apk`（最新版号可能不同，选 universal.apk）

---

## 第二步：配 Termux

打开 Termux，逐行输入（每行回车）：

```bash
termux-setup-storage
pkg update && pkg upgrade -y
pkg install python -y
pkg install vim nano -y
```

等它跑完（可能 5–10 分钟，取决于网络）。

---

## 第三步：把 dunyg 装进去

两个办法：

### 办法 A：curl 直接拉

```bash
cd ~
curl -O https://gitee.com/zhu-meiyan1/luo-shen-ai/raw/master/dunyi_termux.py
```

（如果 curl 在 Termux 里被墙，用办法 B）

### 办法 B：在 Termux 里建文件

```bash
cd ~
nano dunyi_termux.py
```

把代码粘贴进去，`Ctrl+X` → `Y` → 回车保存。

---

## 第四步：跑

```bash
cd ~
ZHIPU_API_KEY=3121fdd55f9340cba35f39fa2e312bc5.c4KrVxtLCPdCgARq python dunyi_termux.py
```

屏幕显示 `dunyi on :8000` 说明起来了。

---

## 第五步：手机浏览器访问

手机 Chrome 打开：

```
http://localhost:8000
```

看到"顿一" 页面，点麦克风说话。

---

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| Connection refused | Termux 里进程没跑 | 重新跑第四步 |
| 浏览器打不开 localhost | 防火墙/浏览器限制 | 试 `127.0.0.1:8000` |
| 麦克风权限被拒 | Chrome 需要授权 | 地址栏左边 → 权限 → 允许麦克风 |
| 中文语音合成不出声 | 浏览器没装中文 TTS | Chrome 设置 → 语言 → 加中文 |
| 息屏后进程被杀 | 系统杀后台 | 见下方"保活" |

---

## 保活（关键）

华为鸿蒙息屏后会杀后台 Termux。这样防：

**设置 → 电池 → 应用启动管理 → Termux → 手动管理 → 三个开关全开：**
- 允许自启动
- 允许关联启动  
- 允许后台活动

另外 Termux 内安装 `termux-wake-lock`：

```bash
pkg install termux-api -y
```

在跑遁一前执行一次：
```bash
termux-wake-lock
```

屏幕常亮时遁一不会被杀。息屏后看华为的严格程度，可能需要保持充电。

---

## 语音功能速查

| 能力 | 浏览器 | 状态 |
|---|---|---|
| 语音识别（你说话 → 文字） | webkitSpeechRecognition, 中文 zh-CN | ✅ Chrome/Edge 支持 |
| 语音合成（回复 → 出声） | speechSynthesis, 中文 | ✅ 浏览器内置 |
| 御姐音/特定音色 | 服务端 edge-tts | ❌ Termux 内接较复杂，先不做 |

---

## 进阶：自跑（不加后台循环）

Termux 单线程跑 asyncio 容易崩。先不跑后台循环。等本地跑通后，再考虑把代码改回带 background_tick 的版本。

---

## 完整 dunyi_termux.py 代码

见仓库根目录 `dunyi_termux.py`。

和主版本差别：
- 去掉 edge-tts，用浏览器 SpeechSynthesis
- 去掉 threading，单线程跑
- 接口不变：GET /, POST /say, GET /tts
