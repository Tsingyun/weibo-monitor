# 岁己SUI 微博监控

本地运行的微博超话在线状态监控工具，支持 **Bark（iOS 原生推送）+ Telegram Bot** 双通道通知、交互式命令、WebUI 数据面板。

## 功能

- **实时监控** — 轮询超话 API（默认 **15 秒**），检测上/下线
- **Bark 推送（推荐）** — 走 Apple APNs，iOS 上比 Bot 更及时可靠；支持副标题、自定义铃声、点击直达微博主页
- **Telegram 通知** — 上/下线即时推送，含在线时长、距上次下线
- **Bot 交互命令** — `/status` `/today` `/stats` `/log` `/daily` `/hourly` `/weekly` `/monthly`
- **图表生成** — Bot 直接回复 PNG 统计图表（每日柱状图 + 24H 分布）
- **WebUI 面板** — 实时状态 / KPI / 每日上线 / 时长趋势 / 24h 分布 / 在线占比 / 覆盖率热力图 / 在线热力图 / **进程健康**
- **去重与去抖** — 状态不变不重复通知；短时抖动（默认 <30 秒）自动抑制噪音推送（事件仍记录）

### 自愈与数据完整性

| 能力 | 说明 |
|------|------|
| 风控退避 | 遭遇微博风控（HTTP 432）**不重试**，改为逐级退避（60s→5m→15m→30m），恢复后自动复位 |
| Cookie 热重载 | Cookie 过期进入暂停态（**不再退出进程**），更新 `.env` 后**自动恢复，无需重启** |
| 事件补写 | events.json 写入失败时事件进内存队列，后续自动补写，**数据不丢** |
| 到期预警 | 解析 Cookie 的 `ALF` 时间戳，剩余不足 3 天主动推送提醒 |
| 代理自检 | 代理（Clash）未启动时快速跳过发送，不再每轮卡满超时 |
| 统计实时化 | stats 每 5 分钟定时刷新，长时间在线时"当前在线时长"持续增长 |
| 跨日界拆分 | 跨凌晨的在线会话按日界拆分归属，"今日在线时长"不再漏算 |
| 进行中会话 | 当前正在线的会话实时计入统计 |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
copy .env.example .env
# 编辑 .env，至少填入 WEIBO_COOKIE

# 3. 启动
python app.py
```

## 获取 Cookie

1. Chrome 打开 https://m.weibo.cn 并**登录**
2. `F12` → `Network` → 刷新页面 → 点选任意请求
3. 在请求头里复制**整段 Cookie**（从 `WEIBOCN_FROM=` 到末尾，分号分隔的一长串）
4. 粘贴到 `.env` 的 `WEIBO_COOKIE`

> **有效期**：由 Cookie 里的 `ALF` 时间戳决定（通常约 30 天）。过期前 3 天会主动预警；
> 过期后只需更新 `.env` 里的值，进程会在几秒内自动热重载恢复，**不用重启**。

## Bot 命令

| 命令 | 功能 |
|------|------|
| `/status` | 当前状态 + 运行时长 + 已离线时长 |
| `/today` | 今日上线次数 + 在线时长 |
| `/stats` | 累计统计摘要 |
| `/log` | 最近 10 条日志 |
| `/daily` | 📊 每日上线次数图表 |
| `/hourly` | 📊 24H 时段分布图 |
| `/weekly` | 本周统计报告 |
| `/monthly` | 本月统计报告 |
| `/help` | 帮助 |

## WebUI

```bash
pip install flask
python web_ui.py
# 浏览器打开 http://localhost:8765
```

面板提供 `/api/stats`、`/api/logs`、`/api/health`（进程健康）、`/api/control`（需 `WEBUI_CONTROL_TOKEN`）。

## 辅助工具

| 脚本 | 用途 |
|------|------|
| `archive_data.py` | 归档过期事件、精简 events.json（历史统计通过聚合保留，不丢） |
| `export_data.py` | 导出 CSV（事件 / 每日 / 会话），便于 Excel 或 pandas 分析 |
| `backfill.py` | 手动补录停机期间缺失的上线数据 |
| `tests/test_core.py` | 核心逻辑单元测试（防回归），`python tests/test_core.py` |

用法示例：

```bash
python archive_data.py 90 --dry-run    # 预览归档 90 天前的数据（不写入）
python export_data.py                  # 导出全部 CSV 到 export/
python backfill.py 2026-08-06 3 --times 09:30,13:15,21:00   # 补录指定日期 3 次上线
```

## 项目结构

```
weibo-monitor/
├── app.py            主入口（进程互斥锁 + UTF-8 强制）
├── monitor.py        监控核心（统计/覆盖率/巡检/退避/热重载/主循环）
├── weibo.py          微博 API（指数退避重试 + 432 风控识别 + Cookie 过期检测）
├── notifier.py       多通道推送（Telegram + Bark 直连绕 Clash TUN/代理自检）
├── tg_commands.py    Bot 交互命令
├── charts.py         图表生成（matplotlib）
├── config.py         环境变量配置
├── utils.py          工具函数（北京时间/逻辑日界/原子写/时长格式化）
├── logger.py         日志系统（RotatingFileHandler）
├── web_ui.py         WebUI 面板（Flask，含健康/控制接口）
├── archive_data.py   数据归档工具
├── export_data.py    数据导出工具（CSV）
├── backfill.py       历史补录工具
├── tests/            单元测试
├── start.bat         Windows 一键启动
├── requirements.txt
├── .env.example      配置模板
└── data/             运行时数据（events/stats/coverage/health/archive）
```

## 配置

所有配置通过 `.env`，见 `.env.example`（含 Bark、退避阶梯、归档、控制接口 token 等）。
