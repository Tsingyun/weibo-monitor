# 岁己SUI 微博监控

本地运行的微博超话在线状态监控工具，支持 Telegram Bot 通知和交互式命令。

## 功能

- **实时监控** — 轮询超话 API（默认 30 秒），检测上下线
- **Telegram 通知** — 上/下线即时推送，含在线时长
- **Bot 交互命令** — `/status` `/today` `/stats` `/log` `/daily` `/hourly`
- **图表生成** — Bot 直接回复 PNG 统计图表（每日柱状图 + 24H 分布）
- **WebUI 面板**（可选）— 浏览器本地数据面板
- **去重保护** — 状态不变不重复通知

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 .env
copy .env.example .env
# 编辑 .env 填入 WEIBO_COOKIE

# 3. 启动（二选一）
双击 start.bat
# 或
python app.py
```

## Bot 命令

在 Telegram 给 `@sui_weibo_bot` 发送：

| 命令 | 功能 |
|------|------|
| `/status` | 当前状态 + 运行时长 |
| `/today` | 今日上线次数 + 在线时长 |
| `/stats` | 累计统计摘要 |
| `/log` | 最近 10 条日志 |
| `/daily` | 📊 每日上线图表 |
| `/hourly` | 📊 24H 时段分布 |
| `/help` | 帮助 |

## WebUI（可选）

```bash
pip install flask
python web_ui.py
# 浏览器打开 http://localhost:8765
```

## 配置

所有配置通过 `.env`，见 `.env.example`。

## 获取 Cookie

1. Chrome 打开 https://m.weibo.cn 登录
2. F12 → Application → Cookies → m.weibo.cn
3. 复制 `SUB`、`SUBP`、`SCF`、`XSRF-TOKEN`
4. 填入 `.env` 的 `WEIBO_COOKIE`

## 项目结构

```
weibo-monitor/
├── app.py          主入口（监控）
├── monitor.py      监控核心
├── weibo.py        微博 API（指数退避重试）
├── notifier.py     Telegram 通知
├── tg_commands.py  Bot 交互命令
├── charts.py       图表生成（matplotlib）
├── config.py       环境变量配置
├── utils.py        工具函数
├── logger.py       日志系统
├── web_ui.py       WebUI 面板（可选）
├── start.bat       Windows 一键启动
├── requirements.txt
├── .env.example    配置模板
└── data/           历史数据和运行时统计
```
