# 岁己SUI 微博监控

监控 B站虚拟主播「岁己SUI」的微博超话在线状态，支持 Telegram 实时通知。

## 功能

- **实时监控** — 轮询微博超话 API（默认 15 秒），检测上下线
- **Telegram 推送** — 上线/下线即时通知，含在线时长
- **指数退避重试** — 网络异常自动恢复，不丢数据
- **每日心跳** — 每天 8:00 发送运行摘要
- **日志系统** — RotatingFileHandler，10MB×10 份自动轮转
- **状态持久化** — 数据保存至 JSON，重启不重复通知
- **资源友好** — 专为 e2-micro 优化，MemoryMax=128M

## 快速开始

```bash
# 安装
cp .env.example .env   # 编辑 .env 填入 WEIBO_COOKIE
bash scripts/install.sh

# 启动
python app.py           # 前台运行
# 或
sudo systemctl start weibo-monitor  # systemd 后台运行
```

## 项目结构

```
weibo-monitor/
├── app.py              主入口
├── monitor.py          监控核心逻辑
├── weibo.py            微博 API（带重试）
├── notifier.py         Telegram 通知（带重试）
├── utils.py            工具函数
├── config.py           配置（环境变量）
├── logger.py           日志系统
├── requirements.txt
├── .env.example        配置模板
├── .gitignore
├── scripts/
│   ├── install.sh      一键部署
│   ├── update.sh       一键更新
│   ├── backup.sh       数据备份
│   └── weibo-monitor.service  systemd 服务文件
└── data/
    └── history.json     历史每日上线数据
```

## 配置

所有配置通过 `.env` 环境变量，详见 `.env.example`。

## 获取 Cookie

1. 打开 Chrome 访问 https://m.weibo.cn 并登录
2. F12 → Application → Cookies → m.weibo.cn
3. 复制 `SUB`、`SUBP`、`SCF`、`XSRF-TOKEN` 的值
4. 拼成 `SUB=...; SUBP=...; SCF=...; XSRF-TOKEN=...` 填入 .env
