#!/usr/bin/env python3
"""历史缺口补录工具（F3）

监控停机 / 数据缺失的日期，可手动补录到 events.json。
补录的事件会正常参与统计（会话配对、每日聚合、覆盖率标注）。

用法:
  python backfill.py 2026-08-06 3
      # 为 2026-08-06 补录 3 次上线（自动分布在白天时段，每次默认 10 分钟）

  python backfill.py 2026-08-06 3 --times 09:30,13:15,21:00
      # 指定每次上线的具体时刻

  python backfill.py 2026-08-06 2 --duration 25
      # 指定每次上线持续 25 分钟

注意：补录会写入 events.json 并重算 stats.json，建议先备份：
  copy data\\events.json data\\events.json.bak
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import EVENT_PATH
from utils import read_json, write_json, beijing_str
from monitor import Monitor


def _default_slots(count):
    """默认把上线时刻较均匀地分布在 9:00~22:00 之间"""
    slots = []
    for i in range(count):
        hour = 9 + (i * 13 // max(1, count))
        slots.append(f"{hour:02d}:00")
    return slots


def backfill(date_str, count, times=None, duration_min=10):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"日期格式错误: {date_str}（应为 YYYY-MM-DD）")
        return

    slots = times.split(",") if times else _default_slots(count)
    slots = [s.strip() for s in slots if s.strip()][:count]

    added = []
    for t in slots:
        try:
            start = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"忽略无效时刻: {t}（应为 HH:MM）")
            continue
        end = start + timedelta(minutes=duration_min)
        added.append({"time": beijing_str(start), "status": "online", "desc1": "补录"})
        added.append({"time": beijing_str(end), "status": "offline", "desc1": "补录"})

    if not added:
        print("没有可补录的事件")
        return

    logs = read_json(EVENT_PATH, [])
    before = len(logs)
    merged = logs + added
    merged.sort(key=lambda e: e.get("time", ""))
    write_json(EVENT_PATH, merged)
    Monitor(log_fn=lambda s: None).save_stats()
    print(f"已为 {date_str} 补录 {len(added) // 2} 次上线（每次 {duration_min} 分钟）")
    print(f"  events.json: {before} → {len(merged)} 条；stats.json 已重算")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    def opt(name, default=None):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

    if len(args) < 2:
        print("用法: python backfill.py <日期 YYYY-MM-DD> <上线次数> [--times 09:30,14:00] [--duration 10]")
        print("例:   python backfill.py 2026-08-06 3 --times 09:30,13:15,21:00")
        return

    date_str, count = args[0], int(args[1])
    backfill(date_str, count, times=opt("--times"),
             duration_min=int(opt("--duration", 10)))


if __name__ == "__main__":
    main()
