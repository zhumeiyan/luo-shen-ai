#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  洛神 AI — 一键启动脚本（Mac / Linux）
#  使用方法：双击此文件，或在终端运行 ./start.sh
# ═══════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

# ─── 颜色 ────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║         神 AI  — 本 地 启 动         ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# ─── 1. 检查 Python ──────────────────────────────────
echo -e "${YELLOW}[1/4] 检查 Python 环境...${NC}"

if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo -e "${RED}错误：未检测到 Python！${NC}"
    echo ""
    echo "请先安装 Python 3.10 或更高版本："
    echo "  官网: https://www.python.org/downloads/"
    echo "  Mac 用户也可以用: brew install python3"
    echo ""
    read -p "按回车键退出..."
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo -e "  ${GREEN}✓ 检测到: $PY_VERSION${NC}"

# ─── 2. 安装依赖 ─────────────────────────────────────
echo -e "${YELLOW}[2/4] 安装依赖...${NC}"
$PYTHON -m pip install --quiet --user requests 2>/dev/null || $PYTHON -m pip install --quiet requests
echo -e "  ${GREEN}✓ requests 已就绪${NC}"

# ─── 3. 检查 ZHIPU_API_KEY ────────────────────────────
echo -e "${YELLOW}[3/4] 检查 API Key...${NC}"

# 优先从 .env 文件读取
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

if [ -z "$ZHIPU_API_KEY" ]; then
    echo -e "  ${YELLOW}⚠ 未检测到 ZHIPU_API_KEY${NC}"
    echo ""
    echo "请输入你的智谱 API Key："
    echo "（获取方式：访问 https://open.bigmodel.cn → 注册 → API Keys）"
    read -p "> " INPUT_KEY
    if [ -z "$INPUT_KEY" ]; then
        echo -e "${RED}错误：API Key 不能为空！${NC}"
        read -p "按回车键退出..."
        exit 1
    fi
    echo "ZHIPU_API_KEY=$INPUT_KEY" > .env
    export ZHIPU_API_KEY="$INPUT_KEY"
    echo -e "  ${GREEN}✓ 已保存到 .env 文件（下次自动读取）${NC}"
else
    # 只显示前8个字符
    KEY_DISPLAY="${ZHIPU_API_KEY:0:8}********"
    echo -e "  ${GREEN}✓ API Key: $KEY_DISPLAY${NC}"
fi

# ─── 4. 启动洛神 ──────────────────────────────────────
echo -e "${YELLOW}[4/4] 启动洛神...${NC}"
echo ""
echo -e "  ${GREEN}洛神正在启动...${NC}"
echo -e "  ${CYAN}等待 3 秒后自动打开浏览器...${NC}"
echo ""

# 启动后台进程
$PYTHON web_chat.py &
LUOSHEN_PID=$!

# 等待服务就绪
sleep 3

# 自动打开浏览器
if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:7860" &>/dev/null &
elif command -v open &>/dev/null; then
    open "http://localhost:7860" &>/dev/null &
fi

echo -e "  ${GREEN}════════════════════════════════════════${NC}"
echo -e "  ${GREEN}  洛神已就绪！${NC}"
echo -e "  ${GREEN}  浏览器: http://localhost:7860${NC}"
echo -e "  ${GREEN}  按 Ctrl+C 停止${NC}"
echo -e "  ${GREEN}════════════════════════════════════════${NC}"
echo ""

# 等待子进程
wait $LUOSHEN_PID
