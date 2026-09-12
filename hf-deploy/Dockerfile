# 洛神 AI — Hugging Face Spaces Dockerfile
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部代码
COPY . .

# 确保入口脚本可执行
RUN chmod +x entrypoint.sh

# Hugging Face Spaces 要求暴露 7860 端口
EXPOSE 7860

# 持久化目录
VOLUME ["/data"]

# 环境变量
ENV PORT=7860
ENV LUOSHEN_DATA=/data

# 入口：先用 entrypoint.sh 创建软链接，再启动服务
CMD ["./entrypoint.sh"]
