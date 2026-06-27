#!/bin/bash
# 岁己SUI 微博监控 - 一键部署脚本
set -e

echo "=== 岁己SUI 微博监控 - 部署 ==="

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "请先安装 Python 3.10+"
    exit 1
fi

# 2. 安装依赖
echo "[1/3] 安装依赖..."
pip install -r requirements.txt -q

# 3. 检查 .env 配置
if [ ! -f .env ]; then
    echo "[2/3] 创建 .env 配置文件..."
    cp .env.example .env 2>/dev/null || true
    echo "  请编辑 .env 填写你的微博 Cookie"
else
    echo "[2/3] .env 已存在"
fi

# 4. 创建数据目录
echo "[3/3] 创建数据目录..."
mkdir -p logs data

echo ""
echo "部署完成！"
echo "启动监控: python app.py"
echo "WebUI: http://localhost:8765"
