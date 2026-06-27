# Telegram 通知模块

import urllib.request
import json
from config import TG_BOT_TOKEN, TG_CHAT_ID

def enabled():
    return bool(TG_BOT_TOKEN and TG_CHAT_ID)

def send(message):
    """发送 Telegram 消息"""
    if not enabled():
        return False
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": TG_CHAT_ID, "text": message}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False

def notify(message):
    """统一通知：控制台 + Telegram"""
    print(message)
    send(message)
