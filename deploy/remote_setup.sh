#!/bin/bash
# ── Oracle Cloud 洛神一键部署脚本（在服务器上运行） ──
# 用法（本地写好运行）：ssh -i <私钥> ubuntu@<IP> 'bash -s' < remote_setup.sh
set -euo pipefail

echo "════════════════════════════════════════════════"
echo "  洛神 AI — Oracle Cloud 服务器部署脚本"
echo "════════════════════════════════════════════════"

# ── 0. 检查 root/sudo ──
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
  echo "[注意] 以 root 运行。建议使用 ubuntu 普通用户。"
else
  SUDO="sudo"
  echo "[✓] 以普通用户运行，将使用 sudo。"
fi

# ── 1. 系统更新 + Python ──
echo ""
echo "[1/6] 安装 Python 3.10+ ..."
$SUDO apt-get update -y -qq
$SUDO apt-get install -y -qq python3 python3-pip python3-venv curl jq
echo "[✓] Python $(python3 --version) 已安装"

# ── 2. 创建项目目录 ──
echo ""
echo "[2/6] 创建项目目录 ~/luoshen-ai ..."
mkdir -p ~/luoshen-ai/active_memory
mkdir -p ~/luoshen-ai/hospital_rules
echo "[✓] 目录已创建"

# ── 3. 部署 systemd 服务（占位，密钥后续替换） ──
echo ""
echo "[3/6] 配置 systemd 服务 ..."
$SUDO tee /etc/systemd/system/luoshen.service > /dev/null << 'EOF'
[Unit]
Description=Luoshen AI Web Service
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/luoshen-ai
ExecStart=/usr/bin/python3 /home/ubuntu/luoshen-ai/web_chat.py
Restart=always
RestartSec=5
Environment=PORT=8765
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ZHIPU_API_KEY 通过.environment文件注入（安全，不写入service文件）
$SUDO systemctl daemon-reload
echo "[✓] systemd 服务已配置"

echo ""
echo "════════════════════════════════════════════════"
echo "  服务器基础配置完成！"
echo "  接下来请从本地上传代码包："
echo ""
echo "  scp -i <私钥> luo-shen-deploy.tar.gz ubuntu@$(hostname -I | awk '{print $1}'):~/"
echo "════════════════════════════════════════════════"
