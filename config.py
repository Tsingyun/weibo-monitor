# 岁己SUI 微博监控 - 配置
# ================================

import os
from dotenv import load_dotenv

load_dotenv()

# 微博 Cookie
WEIBO_COOKIE = os.getenv("WEIBO_COOKIE",
    "SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WhCsdOngH0DUFkVYVmrxOJ75NHD95QcShe01KMN1KBpWs4Dqcj_i--fiKLhiKLsi--Ri-zpiKnci--4iKnNiKysi--Xi-iWi-2Ni--ciKLhi-iW; "
    "SCF=Asqf37nGbPRJrD9oeUe6EM-v7cbFBrQkknWJhY8D5lDYzMU2PiBXQnEcfa6SoUSeqS8OytDT7vf0da2Qmn3fS1c.; "
    "SUB=_2A25HRHVsDeRhGeBK6FEY9ynFzz2IHXVkOIikrDV6PUJbktAYLVrdkW1NR9ERth0AeXF1izab2zYwU6tEi9A2xdQj; "
    "SSOLoginState=1782580540; ALF=1785172540; WEIBOCN_FROM=1110006030; MLOGIN=1; "
    "_T_WM=67092092552; XSRF-TOKEN=9f8e17; "
    "M_WEIBOCN_PARAMS=uicode%3D20000174%26fid%3D102803")

# 微博超话 Container ID
WEIBO_CONTAINERID = "100808f7e22e5e7435023544d44d473e414c10"

# Telegram
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "8998128366:AAFsxyaobKIme0D2bbOJ23gaU5EupoBaGWk")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "361345097")

# 监控
POLL_INTERVAL = 15       # 轮询间隔（秒）
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "weibolog.json")
STATS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stats.json")
HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "history.json")

# WebUI
WEBUI_HOST = "127.0.0.1"
WEBUI_PORT = 8765

# 日界限：岁己作息 ~11:00 起床 ~03:00 入睡
# 凌晨 00:00-03:59 的事件归属前一天
DAY_BOUNDARY_HOUR = 4
