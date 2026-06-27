#!/bin/bash
# 岁己SUI 微博监控 - 一键部署脚本
# 用法: bash scripts/install.sh
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
ok()  { echo -e "${GREEN}[OK]${NC} $*"; }

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

log "岁己SUI 微博监控 - 部署开始"

# ---- 1. Python 环境 ----
log "检查 Python..."
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    log "安装 Python3..."
    sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
    PYTHON=$(command -v python3)
fi
PY_VER=$($PYTHON --version 2>&1)
ok "Python: $PY_VER"

# ---- 2. venv ----
if [ ! -d "venv" ]; then
    log "创建虚拟环境..."
    $PYTHON -m venv venv
fi
source venv/bin/activate
log "安装依赖..."
pip install -r requirements.txt -q
ok "依赖安装完成"

# ---- 3. 配置文件 ----
if [ ! -f .env ]; then
    log "创建 .env..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "  请编辑 .env 填入你的 WEIBO_COOKIE"
    fi
else
    ok ".env 已存在"
fi

# ---- 4. 数据目录 ----
mkdir -p logs data
# 初始化数据文件
[ ! -f data/events.json ] && echo '[]' > data/events.json
[ ! -f data/history.json ] && echo '[]' > data/history.json
ok "数据目录就绪"

# ---- 5. systemd 服务（仅在 Linux 下） ----
if [ -f /etc/os-release ]; then
    SERVICE_FILE="/etc/systemd/system/weibo-monitor.service"
    if [ ! -f "$SERVICE_FILE" ]; then
        log "安装 systemd 服务..."
        sed "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" scripts/weibo-monitor.service | \
        sed "s|ExecStart=.*|ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/app.py|" | \
        sed "s|EnvironmentFile=.*|EnvironmentFile=$PROJECT_DIR/.env|" | \
        sudo tee "$SERVICE_FILE" > /dev/null
        sudo systemctl daemon-reload
        sudo systemctl enable weibo-monitor
        ok "systemd 服务已安装并启用"
    else
        ok "systemd 服务已存在"
    fi
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo ""
echo "  启动服务:  sudo systemctl start weibo-monitor"
echo "  停止服务:  sudo systemctl stop weibo-monitor"
echo "  查看状态:  sudo systemctl status weibo-monitor"
echo "  查看日志:  journalctl -u weibo-monitor -f"
echo -e "${GREEN}========================================${NC}"
