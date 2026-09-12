# PythonAnywhere 上线指南（8 步）

> AI 已完成代码上传和配置。你在网页上完成以下 8 个点击操作即可。

---

## 第 1 步：创建 Web 应用

1. 浏览器打开 **https://www.pythonanywhere.com**，登录
2. 点顶部 **「Web」** 标签
3. 点绿色大按钮 **「Add a new web app」**
4. 选 **「Manual configuration」**（不是 Flask/Django）
5. 选 **Python 3.10**
6. 点 **「Next」**

## 第 2 步：打开终端安装依赖

1. 回到 PythonAnywhere 主面板
2. 点 **「Consoles」** → **「Bash」** → **「Start a new console」**
3. 等终端加载完毕，粘贴这行命令并回车：

```bash
pip install --user requests
```

看到「Successfully installed requests」即成。关闭终端。

## 第 3 步：配置 WSGI 入口文件

> ⚠️ 免费账号无法通过 API 创建 webapp，这一步是必经之路

1. 切回 **「Web」** 标签
2. 找到 **「Code」** 区块中的 **WSGI configuration file**（默认类似 `/var/www/zhumeiyan_pythonanywhere_com_wsgi.py`）
3. 点蓝色链接（路径本身），进入编辑器
4. **删除所有内容**，替换为以下这 2 行：

```python
import sys
sys.path.insert(0, '/home/zhumeiyan/luoshen')
from wsgi import application
```

5. 点右上角 **「Save」** 保存

## 第 4 步：设置环境变量（API Key）

1. 仍在 **「Web」** 标签
2. 找到 **「Environment variables」** 区块
3. 输入 Name: `ZHIPU_API_KEY`
4. 输入 Value: **你的智谱 API Key**（从 https://open.bigmodel.cn → API Keys 复制）
5. 点绿色对勾保存

> ⚠️ 同理可设 `LUOSHEN_DATA = /home/zhumeiyan/luoshen`

## 第 5 步：重载 Web 应用

1. 在 Web 标签顶部，点绿色的 **「Reload」** 按钮
2. 等待 ~30 秒显示 「Working」

## 第 6 步：测试！

浏览器打开 **https://zhumeiyan.pythonanywhere.com**

看到洛神聊天页面的绿底文字框 → 输入文字 → 发送 → 洛神回复。

---

## 出错排查

| 现象 | 原因 | 解决 |
|------|------|------|
| Error 500 / Internal Server Error | 依赖未安装 | 重做第 2 步 |
| 洛神回复「API key 错误」 | ZHIPU_API_KEY 未设置 | 重做第 4 步 |
| Error 404 | WSGI 路径不对 | 确认第 3 步文件路径正确 |
| Bad Gateway | 应用崩溃 | 点 Web 标签下方 「Error log」看详细错误 |
| 网页打开无内容 | 入口没找到 | 确认 WSGI 文件里的路径完全一致 |

---

## 别忘了

- PythonAnywhere 免费账号，3 个月不登录会被暂停
- 如需一直在线，记得每 3 个月登录一次
- 洛神的数据都保存在 `/home/zhumeiyan/luoshen/` 下，不会丢失
