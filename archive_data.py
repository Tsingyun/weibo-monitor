#!/usr/bin/env python3
"""数据归档工具（B5）

把 events.json 中过期的事件移入 data/archive/events_YYYY-MM.json（原始数据可追溯），
并将这些事件产生的「每日聚合」累加进 data/archive/daily_aggregate.json。
监控的 compute_stats 会自动合并该聚合，因此归档后历史统计不丢，
而 events.json 保持精简、统计重算也更快。

安全设计：
- 只归档到「最后一个 offline 事件」为止，避免把一个进行中的会话割裂在两侧导致丢失。
- 默认 ARCHIVE_AFTER_DAYS=0（不自动归档），需手动执行本脚本。

用法:
  python archive_data.py              # 按 .env 的 ARCHIVE_AFTER_DAYS 归档
  python archive_data.py 90           # 归档 90 天前的事件
  python archive_data.py 90 --dry-run # 只预览，不写入任何文件
"""

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (EVENT_PATH, ARCHIVE_DIR, ARCHIVE_DAILY_PATH,
                    ARCHIVE_AFTER_DAYS, DAY_BOUNDARY_HOUR)
from utils import beijing_now, read_json, write_json, logical_date
from monitor import Monitor


def build_daily_aggregate(events, sessions):
    """按逻辑日聚合：online_count / sessions / minutes"""
    daily = defaultdict(lambda: {"online_count": 0, "sessions": 0, "minutes": 0.0})
    for e in events:
        if e.get("status") == "online":
            try:
                dt = datetime.strptime(e["time"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            daily[logical_date(dt, DAY_BOUNDARY_HOUR)]["online_count"] += 1
    for s in sessions:
        daily[s["date"]]["sessions"] += 1
        daily[s["date"]]["minutes"] += s["duration_minutes"]
    return {d: {"online_count": v["online_count"],
                "sessions": v["sessions"],
                "minutes": round(v["minutes"], 1)} for d, v in daily.items()}


def pick_archivable(logs, cutoff):
    """挑出可安全归档的事件（早于 cutoff，且不晚于最后一个 offline 事件）"""
    last_offline_idx = -1
    for idx in range(len(logs) - 1, -1, -1):
        if logs[idx].get("status") == "offline":
            last_offline_idx = idx
            break
    safe_upto = last_offline_idx + 1 if last_offline_idx >= 0 else 0
    old, keep = [], []
    for i, e in enumerate(logs):
        if i < safe_upto and (e.get("time") or "") < cutoff:
            old.append(e)
        else:
            keep.append(e)
    return old, keep


def main():
    days = ARCHIVE_AFTER_DAYS
    dry = "--dry-run" in sys.argv
    for a in sys.argv[1:]:
        if a.lstrip("-").isdigit():
            days = int(a)
    if days <= 0:
        print("未启用归档（ARCHIVE_AFTER_DAYS=0）。")
        print("用法: python archive_data.py <天数> [--dry-run]   例: python archive_data.py 90 --dry-run")
        return

    logs = read_json(EVENT_PATH, [])
    if not logs:
        print("events.json 为空，无需归档")
        return

    cutoff = (beijing_now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    old, keep = pick_archivable(logs, cutoff)
    print(f"总事件 {len(logs)} 条 | 可归档 {len(old)} 条（早于 {cutoff}）| 保留 {len(keep)} 条")
    if not old:
        print("没有需要归档的事件")
        return

    # 复用监控同一套会话配对逻辑，保证归档前后统计口径一致
    m = Monitor(log_fn=lambda s: None)
    sessions = []
    m._build_sessions_from(old, sessions)
    agg = build_daily_aggregate(old, sessions)
    print(f"归档事件产生 {len(sessions)} 个会话，覆盖 {len(agg)} 个日期")

    if dry:
        print("[dry-run] 预览完成，未写入任何文件。前 10 个日期聚合：")
        for d in sorted(agg)[:10]:
            print("   ", d, agg[d])
        return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 1) 原始事件按月写入 archive/events_YYYY-MM.json（追加合并，保持时间有序）
    by_month = defaultdict(list)
    for e in old:
        by_month[(e.get("time") or "")[:7]].append(e)
    for month, items in sorted(by_month.items()):
        path = os.path.join(ARCHIVE_DIR, f"events_{month}.json")
        merged = read_json(path, []) + items
        merged.sort(key=lambda x: x.get("time", ""))
        write_json(path, merged)
        print(f"  已写入 {path}（{len(merged)} 条）")

    # 2) 累加每日聚合
    prev = read_json(ARCHIVE_DAILY_PATH, {})
    for d, v in agg.items():
        if d in prev:
            prev[d]["online_count"] += v["online_count"]
            prev[d]["sessions"] += v["sessions"]
            prev[d]["minutes"] = round(prev[d]["minutes"] + v["minutes"], 1)
        else:
            prev[d] = v
    write_json(ARCHIVE_DAILY_PATH, prev)
    print(f"  已更新聚合 {ARCHIVE_DAILY_PATH}（累计 {len(prev)} 个日期）")

    # 3) 精简 events.json
    write_json(EVENT_PATH, keep)
    print(f"  events.json 已精简为 {len(keep)} 条")
    print("归档完成。统计会自动合并 archive/daily_aggregate.json，历史数据不丢。")


if __name__ == "__main__":
    main()
