#!/bin/bash
# 岁己SUI 微博监控 - 一键更新脚本
set -e
echo "=== 更新代码 ==="
git pull origin main
pip install -r requirements.txt -q
echo "更新完成。重启 app.py 即可。"
