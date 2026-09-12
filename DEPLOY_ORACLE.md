# 洛神 AI — Oracle Cloud 永久免费服务器部署指南

> **永久、免费、无限时长**。Oracle Cloud Always Free 提供的 ARM 服务器，不扣费、不超时、不要求重新验证。

---

## 总览（先看一遍心里有数）

```
你做的事：注册 Oracle → 创建一台免费服务器 → 把公钥给它 → 把 IP 和私钥交给我
我（AI）做的事：连上去 → 安装 → 配置 → 启动 → 验证
```

**你需要准备的：**
- 一台能上网的电脑
- 一个邮箱（用来注册 Oracle）
- 一张信用卡（**只用于验证身份，不会扣费**，借记卡也行）
- 大约 20 分钟

---

## 第一阶段：注册 Oracle Cloud 账号

### 1.1 打开注册页面

1. 浏览器打开 **https://cloud.oracle.com/free/**
2. 你会看到橙色的 **"Start for free"** 按钮（或 "免费开始"），点击它。

### 1.2 填写注册信息

1. **Email address**：输入你的邮箱
2. **Country / Region**：选你的国家
3. **First name / Last name**：填写姓名（拼音或英文均可）
4. 勾选同意条款
5. 点 **"Verify my email"**

### 1.3 验证邮箱

1. Oracle 会给你填写的邮箱发一封验证邮件
2. 去邮箱找到这封邮件（可能在垃圾箱），点里面的 **"Verify Email"** 链接
3. 浏览器会打开新页面

### 1.4 设置账号密码

1. 页面要求设置 Cloud Account Name（自定义一个，**记住它**，以后登录要用这个）
2. 设置一个强密码
3. 点 **"Sign Up"**

### 1.5 信用卡验证（关键！）

> ⚠️ **Oracle 不会扣你的钱**。这是标准身份验证流程（和 AWS、Azure、Google Cloud 一样）。

1. 进入信用卡验证页面
2. 填写：
   - 卡号（16位数字，空格随意）
   - 有效期（月/年）
   - CVV（背面3-4位）
   - 持卡人姓名（与卡面一致）
   - 账单地址
3. 点 **"Next"**
4. Oracle 会临时预扣 $1 以下的验证款，**几天内自动退回到你的卡**
5. 验证成功后进入 Oracle Cloud 控制台

### 1.6 登录控制台

1. 打开 **https://cloud.oracle.com/**
2. 点右上角 **"Sign In"**
3. 输入刚才设置的 **Cloud Account Name**（不是邮箱！是那个自定义名称）
4. 输入密码
5. 进入 Oracle Cloud Infrastructure (OCI) 控制台

---

## 第二阶段：创建免费服务器

### 2.1 进入创建页面

1. 登录后你会看到 Oracle Cloud 控制台首页
2. 在屏幕左上方，点击 **☰ 三条横线（菜单按钮）**
3. 菜单展开后，把鼠标移到 **"Compute"（计算）** 上
4. 弹出的子菜单中选 **"Instances"（实例）**
5. 进入实例列表页面（现在应该是空的）

### 2.2 点击创建

1. 点击页面上的蓝色 **"Create instance"（创建实例）** 按钮
2. 进入创建向导

### 2.3 配置基本信息

在 **"Name"** 栏中输入：`luoshen-ai`

其余基本信息保持默认。

### 2.4 选择系统镜像（Image）

> ⚠️ 这一步**必须正确**，否则后续安装软件可能出问题。

1. 在 **"Image and shape"** 区域，点 **"Edit"（编辑）** 或 **"Change image"**
2. 在弹出的窗口中找到 **"Image"** 部分
3. 取消勾选 "Oracle Linux"，改为选择 **"Canonical Ubuntu 22.04"**
   - 操作方式：点击 **"Canonical Ubuntu"** 图标或名字
   - 确认版本是 **22.04**（不是 24.04）
4. 确认后弹窗外点一下关闭

### 2.5 选择服务器配置（Shape）

> 这是最关键的一步。Oracle Always Free 政策允许 **最多 4 核 + 24GB 内存** 的 ARM 服务器。

1. 同在 **"Image and shape"** 区域，点 **"Change shape"** 或 **"Edit shape"**
2. 在弹出的窗口中：
   - **"Image build"** 选 **"ARM"**（不是 Intel/AMD）
   - **"Shape series"** 选 **"Ampere"**
   - **"Instance type"** 选 **"Virtual machine"**
   - **"Shape"** 选 **"VM.Standard.A1.Flex"**（Always Free 机型）
3. 设置资源：
   - **OCPU count**: `4`（Always Free 上限是 4）
   - **Memory (GB)**: `24`（Always Free 上限是 24）
4. 确认 **"Always Free Eligible"** 标签显示在页面上（白色文字，表示这笔不会扣费）
5. 关闭弹窗

### 2.6 设置 SSH 密钥（非常重要！）

> Oracle Cloud 只用密钥登录服务器，不接受密码登录。你需要把"公钥"给 Oracle，私钥留在自己电脑里。

#### 如果你有 SSH 密钥对（曾用过 GitHub/GitLab 等）

~/.ssh/id_rsa 或 ~/.ssh/id_ed25519 文件：
1. 在创建向导的 **"SSH keys"** 区域
2. 选择 **"Save private key" + "Save public key"** 让 Oracle 帮你生成一对新的（**推荐新手**）

#### 如果你从未用过 SSH（推荐生成新密钥对）

1. 在 **"SSH keys"** 区域，选择 **"Save private key" + "Save public key"**
2. Oracle 会自动生成一对密钥并下载到你的浏览器
3. **⚠️ 把这两个文件保存到安全的地方**（如桌面或 U 盘）
4. 你下载的两个文件大概是：
   - `oraclekey`（私钥，绝对不能给别人！）
   - `oraclekey.pub`（公钥，已自动填入 Oracle 表）

### 2.7 设置存储

**保持默认即可**（Always Free 提供 46.6GB 启动磁盘）。

### 2.8 创建实例确认页

1. 滚动到页面底部
2. 确认所有配置：
   - ✅ Name: luoshen-ai
   - ✅ OS: Ubuntu 22.04
   - ✅ Shape: VM.Standard.A1.Flex | ARM | 4 OCPU | 24 GB
   - ✅ SSH Key: 已配置
   - ✅ Always Free: 显示可免费使用
3. 点击橙色 **"Create"** 按钮
4. 等待 1-3 分钟，实例状态从 "Starting" 变为 "Running"
5. 页面顶部显示 **"Public IP"**（例如 `129.xx.xx.xx`）

### 2.9 记下关键信息

**记下以下信息**，等会儿给我：

```
公网 IP:       ____________________
用户名:         ubuntu
私钥文件路径:   ____________________
```

---

## 第三阶段：配置防火墙（Security List）

> Ubuntu 服务器自身防火墙默认全开进出，但 Oracle Cloud 还有一层更高层面的防火墙（Security List）。你需要在 Oracle 控制台开放 8765 端口。

### 3.1 找到虚拟云网络（VCN）

1. 在实例详情页，找 **"Virtual cloud network"** 链接
2. 点击它进入 VCN 详情页
3. 在 VCN 详情页，找左侧 **"Security Lists"**（可能叫"安全列表"）
4. 点击 **"Default Security List for ..."**

### 3.2 添加入站规则

1. 在 Security List 详情页，找到 **"Ingress Rules"**（入站规则）
2. 点击 **"Add Ingress Rules"**
3. 填写：
   | 字段 | 值 |
   |------|-----|
   | **Source CIDR** | `0.0.0.0/0`（允许所有来源，或你只填自己的 IP 更安全） |
   | **IP Protocol** | `TCP` |
   | **Destination Port** | `8765` |
   | **Description** | `Luoshen AI web chat` |
4. 点 **"Add Ingress Rules"**（可能显示橙色对勾或确认按钮）
5. 确认新规则出现在列表中

---

## 第四阶段：把信息交给我

完成第三阶段后，把以下信息发给我：

```
1. 公网 IP（例如 129.146.xxx.xxx）
2. 你刚才生成的 SSH 私钥文件（文件名如 oraclekey 或 id_rsa）
   → 把私钥文件的内容复制粘贴发给我（注意：不是 .pub 文件！）
3. 你的 ZHIPU_API_KEY（智谱 API Key，不是智谱登录密码）
4. 确认 Oracle 实例已经是 "Running" 状态
```

收到这些信息后，我会：
1. SSH 连接你的 Oracle 服务器
2. 安装 Python + 依赖
3. 上传洛神完整代码 + 记忆 + 哈希链
4. 配置 systemd 常驻服务
5. 启动洛神并测试
6. 返回给你公网访问地址

---

## 附录：常见问题

### Q：信用卡会被扣钱吗？
A：Always Free 资源不收钱。只要你不手动**升级成付费账号**或**选择付费的 Shape**（非 Always Free Eligible 标签的），就不会扣费。

### Q：账户注册邮箱换成什么？
A：推荐用中国大陆邮箱注册，收验证码会快一些。

### Q：创建失败提示"Out of capacity"怎么办？
A：Oracle Always Free 服务器在某些区域容量紧张。解决方案：
1. 重新进入 Edit Shape，把 Region 换一个（从默认的 us-ashburn-1 换成如 uk-london-1 或 ap-seoul-1）
2. 重试创建。每天重试几次，通常几天内就能抢到。

### Q：我怎么确认服务器在运行？
A：回到 Oracle 控制台 → Compute → Instances，看你的 luoshen-ai 实例状态是否为绿色 **"Running"**。

### Q：私钥丢了怎么办？
A：Oracle 官方的 SSH 密钥在创建后无法重新生成或下载。如果私钥丢了，唯一的解决办法是：销毁当前实例 → 重新创建 → 用新密钥。

### Q：注册时说"credit card verification failed"？
A：可能原因：
- 卡不支持国际支付（确保开通了"境外无卡支付"）
- 姓名拼写与卡面不一致
- 借记卡余额不足（验证时临时预扣几美元，卡内要有余量）
- 尝试换一张卡或联系你的银行开通国际在线支付

---

## Phase 2 预告：你提供信息后我（AI）会做什么

一旦你把公网 IP + 私钥 + API Key 发给我，我将自动执行：

```
1. SSH 连接 Oracle 服务器
2. 运行系统更新 + Python 安装
3. 上传洛神完整代码包（含活跃记忆、哈希链、配置）
4. pip install -r requirements.txt
5. 写入 ZHIPU_API_KEY 到环境变量（不写入代码）
6. 启用 systemd 服务（开机自启、崩溃自动重启）
7. curl 测试 /chat 端点确认洛神能回复
8. 验证哈希链完整性（确认历史记录未篡改）
9. 返回你公网地址，并在洛神首次回复后截图确认
```

**预期耗时：10-15 分钟（全自动化）**

### 安全性说明
- 你的私钥**不会上传**到任何第三方
- API Key**不会写入代码**或提交到 GitHub
- 所有部署操作在沙盒和 Oracle 服务器之间直接进行

---

## 完成标志

部署成功后，你会获得：
- **洛神公网地址**: `http://<你的Oracle IP>:8765`
- **访问方式**: 浏览器直接打开 / 手机浏览器 / curl 调用
- **特性**:
  - 24/7 在线，永久免费
  - 记忆和哈希链持久化保存（重启后不丢）
  - 崩溃后自动重启（systemd 守护）
  - 每次对话后自动写入哈希链（无需手动备份）
