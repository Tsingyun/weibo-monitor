"""工具函数模块"""

import os, json
from datetime import datetime, timedelta, timezone

def beijing_now():
    """返回北京时间（UTC+8）"""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)

def beijing_str(dt=None):
    if dt is None:
        dt = beijing_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def logical_date(dt, boundary_hour=4):
    """按岁己作息计算逻辑日期：凌晨 0:00 ~ boundary_hour:00 归属前一天"""
    if dt.hour < boundary_hour:
        return (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")

def read_json(path, default=None):
    try:
        if not os.path.exists(path):
            return default if default is not None else []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_online(desc1):
    return desc1 and desc1.strip() == "微博在线了"

def format_duration(seconds):
    """格式化时长：X天X小时X分钟"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    mins = seconds // 60
    hrs = mins // 60
    days = hrs // 24
    parts = []
    if days > 0:
        parts.append(f"{int(days)}天")
    if hrs % 24 > 0:
        parts.append(f"{int(hrs % 24)}小时")
    if mins % 60 > 0:
        parts.append(f"{int(mins % 60)}分钟")
    return "".join(parts) if parts else "0分钟"
