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
    """判断在线状态（容错匹配，防止微博改文案后漏检）"""
    if not desc1:
        return False
    desc1 = desc1.strip()
    # 精确匹配
    if desc1 == "微博在线了":
        return True
    # 容错：包含"在线了"且不含时间前缀词（排除各种过去时态）
    #   n分钟/小时前在线了、昨天/前天HH:MM在线了、n天前在线了 → 均为离线
    _offline_prefixes = ("前", "昨天", "前天", "天前")
    if "在线了" in desc1 and not any(p in desc1 for p in _offline_prefixes):
        return True
    # 容错：微博在线（无"了"）
    if desc1 == "微博在线":
        return True
    return False

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
