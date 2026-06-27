# 岁己SUI 微博监控 - 配置（全部通过环境变量读取）

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ===== 必填配置（无默认值，启动即校验）=====
WEIBO_COOKIE = os.getenv("WEIBO_COOKIE")
if not WEIBO_COOKIE:
    raise RuntimeError("❌ 缺少 WEIBO_COOKIE，请在 .env 中设置")

WEIBO_CONTAINERID = os.getenv("WEIBO_CONTAINERID", "100808f7e22e5e7435023544d44d473e414c10")

# ===== 可选配置 =====
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

POLL_INTERVAL = int(os.getenv("CHECK_INTERVAL", "15"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "3"))

# 日界限（岁己作息 ~11:00起 ~03:00睡，凌晨4:00为日分界）
DAY_BOUNDARY_HOUR = int(os.getenv("DAY_BOUNDARY_HOUR", "4"))

# 心跳时间（每日 08:00 发送运行状态）
HEARTBEAT_HOUR = int(os.getenv("HEARTBEAT_HOUR", "8"))
HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true"

# 路径
import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))
LOG_PATH = _os.path.join(BASE_DIR, "logs", "monitor.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))

DB_PATH = _os.path.join(BASE_DIR, "data", "state.json")
STATS_PATH = _os.path.join(BASE_DIR, "data", "stats.json")
HISTORY_PATH = _os.path.join(BASE_DIR, "data", "history.json")
