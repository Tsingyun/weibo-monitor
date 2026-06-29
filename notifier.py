"""Telegram 通知模块 - 带重试和长消息自动分段"""

import time
import json
import urllib.request
import urllib.error
from config import TG_BOT_TOKEN, TG_CHAT_ID, REQUEST_TIMEOUT

TELEGRAM_MAX_LENGTH = 4096

def enabled():
    return bool(TG_BOT_TOKEN and TG_CHAT_ID)

def _chunk_message(text, max_len=TELEGRAM_MAX_LENGTH):
    """将长消息按段落边界切成多段"""
    if len(text.encode('utf-8')) <= max_len:
        return [text]
    chunks = []
    lines = text.split('\n')
    current = ""
    for line in lines:
        test = current + ('\n' if current else '') + line
        if len(test.encode('utf-8')) > max_len:
            if current:
                chunks.append(current)
                current = line
            else:
                # 单行超长 → 强制截断
                while len(line.encode('utf-8')) > max_len:
                    chunks.append(line[:max_len//2])
                    line = line[max_len//2:]
                current = line
        else:
            current = test
    if current:
        chunks.append(current)
    return chunks

def _send_one(message, log_fn=None):
    """发送单条消息（内部，带重试）"""
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

def send(message, log_fn=None):
    """发送 Telegram 消息（超长自动分段，带重试）"""
    if not enabled():
        return False
    chunks = _chunk_message(message)
    if len(chunks) > 1 and log_fn:
        log_fn(f"消息超长，分成 {len(chunks)} 段发送")
    ok = True
    for i, chunk in enumerate(chunks):
        text = chunk if len(chunks) == 1 else f"[{i+1}/{len(chunks)}] {chunk}"
        if not _send_one(text, log_fn=log_fn):
            ok = False
    return ok

def notify(message, log_fn=None):
    """统一通知：控制台 + Telegram"""
    print(message)
    send(message, log_fn=log_fn)
