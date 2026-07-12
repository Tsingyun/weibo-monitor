# 岁己SUI 微博监控 - 配置（全部通过环境变量读取）

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ===== 基础路径 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ===== 必填配置（无默认值，启动即校验）=====
WEIBO_COOKIE = os.getenv("WEIBO_COOKIE")
if not WEIBO_COOKIE:
    raise RuntimeError("缺少 WEIBO_COOKIE，请在 .env 中设置")

WEIBO_CONTAINERID = os.getenv("WEIBO_CONTAINERID", "100808f7e22e5e7435023544d44d473e414c10")

# ===== 可选配置 =====
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# Bark 推送（iOS 原生推送，替代/补充 Telegram，走 Apple APNs 比 Bot 更可靠）
# 仅需 BARK_KEY；默认用公共服务器 api.day.app，自建时设 BARK_SERVER 为你的域名
BARK_KEY = os.getenv("BARK_KEY", "")
BARK_SERVER = os.getenv("BARK_SERVER", "https://api.day.app").rstrip("/")
BARK_ICON_URL = os.getenv("BARK_ICON_URL", "https://raw.githubusercontent.com/Tsingyun/weibo-monitor/main/assets/bark_icon.png")
BARK_SOUND_URL = os.getenv("BARK_SOUND_URL", "https://cdn.jsdelivr.net/gh/Tsingyun/weibo-monitor@main/assets/bark_sound.mp3")
# 点击推送时跳转的地址（岁己微博主页，手机可直达）。如需点开本地面板可改为 http://localhost:8765
BARK_CLICK_URL = os.getenv("BARK_CLICK_URL", "https://m.weibo.cn/u/7785772638")

# ===== 代理 & 超时（可选）=====
# 在受限网络下（如 api.day.app 连不上），可让 Bark/Telegram 走代理访问
#   直接设 BARK_PROXY / TELEGRAM_PROXY；留空则自动读取系统 HTTPS_PROXY/https_proxy 环境变量
# 例: BARK_PROXY=http://127.0.0.1:7890
def _first_env(*names, default=""):
    for _n in names:
        _v = os.getenv(_n)
        if _v:
            return _v
    return default
BARK_PROXY = os.getenv("BARK_PROXY", _first_env("HTTPS_PROXY", "https_proxy"))
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", _first_env("HTTPS_PROXY", "https_proxy"))
# Bark 推送超时（秒）：api.day.app 在某些网络下连不上，缩短超时避免阻塞主轮询
BARK_TIMEOUT = int(os.getenv("BARK_TIMEOUT", "8"))

POLL_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "3"))

# 日界限（岁己作息 ~11:00起 ~03:00睡，凌晨4:00为日分界）
DAY_BOUNDARY_HOUR = int(os.getenv("DAY_BOUNDARY_HOUR", "4"))

# 心跳时间（每日 08:00 发送运行状态）
HEARTBEAT_HOUR = int(os.getenv("HEARTBEAT_HOUR", "8"))
HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true"

# 日志路径
LOG_PATH = os.path.join(BASE_DIR, "logs", "monitor.log")       # 文本日志（RotatingFileHandler）
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))

# 数据路径
EVENT_PATH = os.path.join(BASE_DIR, "data", "events.json")     # JSON 事件日志（监控数据）
STATS_PATH = os.path.join(BASE_DIR, "data", "stats.json")      # 统计缓存
HISTORY_PATH = os.path.join(BASE_DIR, "data", "history.json")  # 历史每日数据
COVERAGE_PATH = os.path.join(BASE_DIR, "data", "coverage.json") # 监控覆盖率记录（5分钟粒度）

# 覆盖率分桶粒度（分钟）
COVERAGE_BUCKET_MINUTES = int(os.getenv("COVERAGE_BUCKET_MINUTES", "5"))
# 单日视为"疑似缺失"的事件数阈值（低于此值该天数据可能不完整）
MISSING_EVENT_THRESHOLD = int(os.getenv("MISSING_EVENT_THRESHOLD", "3"))
