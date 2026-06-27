# 岁己SUI 微博监控

监控 B站虚拟主播「岁己SUI」(UID:7785772638) 的微博超话在线状态，支持 Telegram 实时通知和本地 WebUI 数据面板。

## 功能

- **微博在线监控** — 每 15 秒轮询超话 API，检测上下线状态
- **Telegram 通知** — 状态变更时实时推送到 Telegram
- **WebUI 数据面板** — 本地网页展示在线状态、每日上线次数、时段分布、历史日志
- **数据统计** — 在线时长、活跃天数、24H 时段分布
- **历史数据整合** — 2025/1 至今的每日上线次数（已按岁己作息调整日界限）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 .env（填写微博 Cookie）
cp .env.example .env  # 如果没有也不影响，Cookie 已内置在代码中

# 3. 启动
python app.py
```

启动后：
- 监控进程运行在终端中
- WebUI 自动启动在 `http://localhost:8765`
- 状态变更时 Telegram 推送通知

## 项目结构

```
weibo-monitor/
├── app.py              # 主程序（监控 + 统计 + WebUI）
├── config.py           # 配置读取
├── notifier.py         # Telegram 推送
├── weibo.py            # 微博 API 请求
├── requirements.txt
├── .env                # 环境变量（不提交）
├── .gitignore
├── data/
│   ├── history.json    # 历史每日上线数据
│   └── stats.json      # 运行时统计缓存
├── logs/
│   └── weibolog.json   # 原始状态日志
└── scripts/
    ├── install.sh      # 一键部署
    └── update.sh       # 一键更新
```

## 日界限规则

岁己作息大约 11:00 起床 ~03:00 入睡。每日上线统计以**凌晨 4:00**为日分界：
- 2026-06-27 11:00 ~ 2026-06-28 03:59 → 归属 2026-06-27
- 2026-06-28 04:00 起 → 归属 2026-06-28

## 技术栈

- Python 3.10+
- Flask（WebUI 服务）
- Chart.js（每日上线柱状图）
- Telegram Bot API（通知推送）
