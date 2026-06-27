#!/bin/bash
# 岁己SUI 微博监控 - 一键更新脚本
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== 更新代码 ==="
git pull origin main

echo "=== 安装新依赖 ==="
source venv/bin/activate
pip install -r requirements.txt -q

echo "=== 重启服务 ==="
if systemctl is-active --quiet weibo-monitor 2>/dev/null; then
    sudo systemctl restart weibo-monitor
    sleep 2
    sudo systemctl status weibo-monitor --no-pager -l
else
    echo "服务未运行，跳过重启"
fi

echo "更新完成。"
