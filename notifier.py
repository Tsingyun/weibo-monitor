"""Telegram 通知模块 - 带重试"""

import time
import json
import urllib.request
import urllib.error
from config import TG_BOT_TOKEN, TG_CHAT_ID, REQUEST_TIMEOUT

def enabled():
    return bool(TG_BOT_TOKEN and TG_CHAT_ID)

def send(message, log_fn=None):
    """发送 Telegram 消息（带重试，指数退避）"""
    if not enabled():
        return False
    for attempt in range(3):
        try:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = json.dumps({"chat_id": TG_CHAT_ID, "text": message}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    return True
                if log_fn:
                    log_fn(f"Telegram API 返回错误: {result}")
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError) as e:
            if log_fn:
                log_fn(f"Telegram 发送失败 (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(min(2 ** attempt, 10))
    return False

def notify(message, log_fn=None):
    """统一通知：控制台 + Telegram"""
    print(message)
    send(message, log_fn=log_fn)
