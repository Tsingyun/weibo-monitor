#!/bin/bash
# 岁己SUI 微博监控 - 自动备份脚本
# 用法: bash scripts/backup.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${PROJECT_DIR}/backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/weibo-monitor_${TIMESTAMP}.tar.gz"

# 备份数据文件和配置
tar -czf "$BACKUP_FILE" \
    -C "$PROJECT_DIR" \
    data/ \
    logs/weibolog.json \
    .env 2>/dev/null || true

echo "备份完成: $BACKUP_FILE"
ls -lh "$BACKUP_FILE"

# 保留最近 30 份备份
ls -t "${BACKUP_DIR}"/weibo-monitor_*.tar.gz 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true
