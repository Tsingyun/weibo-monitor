"""Telegram Bot 命令处理 — 轮询 getUpdates"""

import json
import urllib.request
import ssl
from config import TG_BOT_TOKEN, TG_CHAT_ID, REQUEST_TIMEOUT
from utils import beijing_str, beijing_now, format_duration
from datetime import timedelta

_OFFSET_FILE = None  # 由 init() 设置

def init(storage_dir):
    global _OFFSET_FILE
    import os
    _OFFSET_FILE = os.path.join(storage_dir, "tg_offset.txt")

def _load_offset():
    try:
        with open(_OFFSET_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return 0

def _save_offset(v):
    with open(_OFFSET_FILE, "w") as f:
        f.write(str(v))

def _tg_call(method, params=None):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}"
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"ok": False}

def _send(chat_id, text):
    _tg_call("sendMessage", {"chat_id": chat_id, "text": text})

def _send_photo(chat_id, photo_bytes, caption=""):
    """发送图片（multipart/form-data）"""
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{chat_id}\r\n"
    )
    if caption:
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"{caption}\r\n"
        )
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="photo"; filename="chart.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    )
    body = body.encode("utf-8") + photo_bytes + f"\r\n--{boundary}--\r\n".encode()

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"ok": False}

def handle_command(text, monitor):
    """解析并执行命令，返回 (响应文本, 图片bytes或None)"""
    cmd = text.strip().lower().split()[0] if text else ""

    if cmd == "/help":
        return (
            "岁己SUI 微博监控 · Bot 命令\n\n"
            "/status - 当前在线状态\n"
            "/today - 今日上线统计\n"
            "/stats - 累计统计摘要\n"
            "/log - 最近 10 条日志\n"
            "/daily - 每日上线次数图表\n"
            "/hourly - 24H 时段分布图\n"
            "/help - 显示此帮助"
        ), None

    if cmd == "/status":
        s = "在线 🟢" if monitor.last_status == "online" else "离线 🔴"
        elapsed = format_duration((beijing_now() - monitor.start_time).total_seconds())
        return (
            f"岁己SUI 微博监控\n\n"
            f"当前状态: {s}\n"
            f"最后事件: {monitor.last_desc1 or '未知'}\n"
            f"运行时间: {elapsed}\n"
            f"累计检查: {monitor.total_checks} 次\n"
            f"累计通知: {monitor.total_notifications} 次"
        ), None

    if cmd == "/today":
        stats = monitor.compute_stats()
        t = stats.get("today", {})
        if stats.get("empty"):
            return "暂无数据", None
        return (
            f"今日统计 · {t.get('date', '?')}\n\n"
            f"上线次数: {t.get('online_count', 0)} 次\n"
            f"在线会话: {t.get('sessions', 0)} 次\n"
            f"在线时长: {'{:.0f}'.format(t.get('minutes', 0))} 分钟"
        ), None

    if cmd == "/stats":
        stats = monitor.compute_stats()
        if stats.get("empty"):
            return "暂无数据", None
        total_min = stats.get("total_online_minutes", 0)
        return (
            f"累计统计\n\n"
            f"总事件数: {stats.get('total_events', 0)}\n"
            f"在线会话: {stats.get('total_sessions', 0)} 次\n"
            f"累计在线: {format_duration(int(total_min * 60))}\n"
            f"活跃天数: {stats.get('total_active_days', 0)} 天"
        ), None

    if cmd == "/log":
        logs = monitor.read_log()[-10:]
        if not logs:
            return "暂无日志", None
        lines = []
        for l in reversed(logs):
            emoji = "🟢" if l["status"] == "online" else "🔴"
            lines.append(f"{emoji} {l['time']}  {l['desc1'] or ''}")
        return "最近日志\n\n" + "\n".join(lines), None

    if cmd == "/daily":
        stats = monitor.compute_stats()
        if stats.get("empty"):
            return "暂无数据", None
        try:
            from charts import daily_chart
            buf = daily_chart(stats)
            if buf:
                return "每日上线次数", buf.getvalue()
        except ImportError:
            return "图表功能需要 matplotlib 库\n请在服务器上执行: pip install matplotlib", None
        except Exception as e:
            return f"图表生成失败: {e}", None
        return "暂无图表数据", None

    if cmd == "/hourly":
        stats = monitor.compute_stats()
        if stats.get("empty"):
            return "暂无数据", None
        try:
            from charts import hourly_chart
            buf = hourly_chart(stats)
            if buf:
                return "24H 在线时段分布", buf.getvalue()
        except ImportError:
            return "图表功能需要 matplotlib 库\n请在服务器上执行: pip install matplotlib", None
        except Exception as e:
            return f"图表生成失败: {e}", None
        return "暂无图表数据", None

    return None, None  # 未知命令

def check_updates(monitor):
    """检查并处理 Telegram 新消息（在主循环中调用）"""
    if not TG_BOT_TOKEN:
        return
    offset = _load_offset()
    result = _tg_call("getUpdates", {"offset": offset, "timeout": 1, "allowed_updates": ["message"]})
    if not result.get("ok"):
        return
    for update in result.get("result", []):
        _save_offset(update["update_id"] + 1)
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "")
        if not text.startswith("/"):
            continue
        text_resp, photo_bytes = handle_command(text, monitor)
        if photo_bytes:
            _send_photo(chat_id, photo_bytes, caption=text_resp or "")
        elif text_resp:
            _send(chat_id, text_resp)
