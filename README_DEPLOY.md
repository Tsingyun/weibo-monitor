# 部署指南 — 岁己SUI 微博监控

## 服务器要求

- Ubuntu 20.04+ / Debian 11+（推荐 Google Cloud e2-micro）
- Python 3.8+
- 可用内存 ≥ 128 MB
- 可用磁盘 ≥ 200 MB

## 快速部署

```bash
# 1. 克隆
git clone https://github.com/Tsingyun/weibo-monitor.git
cd weibo-monitor

# 2. 配置 .env
cp .env.example .env
nano .env
# 必填: WEIBO_COOKIE=你的Cookie

# 3. 一键安装
bash scripts/install.sh

# 4. 启动
sudo systemctl start weibo-monitor

# 5. 验证
sudo systemctl status weibo-monitor
```

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `WEIBO_COOKIE` | ✅ | — | 微博登录 Cookie（F12 → Application → Cookies） |
| `TG_BOT_TOKEN` | — | — | Telegram Bot Token（@BotFather 创建） |
| `TG_CHAT_ID` | — | — | Telegram Chat ID（@userinfobot 获取） |
| `CHECK_INTERVAL` | — | `15` | 轮询间隔（秒） |
| `REQUEST_TIMEOUT` | — | `15` | 请求超时（秒） |
| `RETRY_COUNT` | — | `3` | 重试次数 |
| `LOG_LEVEL` | — | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `HEARTBEAT_ENABLED` | — | `true` | 是否发送每日心跳 |
| `HEARTBEAT_HOUR` | — | `8` | 心跳发送时间（小时，北京时间） |

## 常用命令

```bash
# systemd 管理
sudo systemctl start weibo-monitor     # 启动
sudo systemctl stop weibo-monitor      # 停止
sudo systemctl restart weibo-monitor   # 重启
sudo systemctl status weibo-monitor    # 状态
sudo systemctl enable weibo-monitor    # 开机自启

# 查看日志
journalctl -u weibo-monitor -f         # 实时日志
journalctl -u weibo-monitor -n 50      # 最近 50 条
tail -f logs/monitor.log               # 文件日志

# 更新代码
bash scripts/update.sh

# 备份数据
bash scripts/backup.sh
```

## 修改 Cookie

```bash
nano .env                          # 修改 WEIBO_COOKIE
sudo systemctl restart weibo-monitor  # 重启生效
```

## 故障排查

| 问题 | 排查方法 |
|------|----------|
| 服务无法启动 | `journalctl -u weibo-monitor -n 30` |
| 微博返回登录页 | Cookie 已过期，需重新获取 |
| Telegram 收不到 | 检查 TG_BOT_TOKEN 和 TG_CHAT_ID |
| CPU 过高 | 增大 CHECK_INTERVAL（如 30） |
| 内存不足 | 检查 MemoryMax 限制，必要时调高 |

## 备份恢复

```bash
# 备份（自动保留最近 30 份）
bash scripts/backup.sh

# 恢复（假设 backups/weibo-monitor_20260628_120000.tar.gz）
tar -xzf backups/weibo-monitor_20260628_120000.tar.gz -C /opt/weibo-monitor/
sudo systemctl restart weibo-monitor
```

## 安全建议

- 不要将 `.env` 提交到 Git
- 使用 `ufw` 仅开放 22 端口
- 定期轮换 Telegram Bot Token
- 定期备份 `data/` 和 `logs/`
