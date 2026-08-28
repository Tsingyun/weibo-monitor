#!/usr/bin/env python3
"""数据导出工具（F2）— 导出 CSV，便于用 pandas / Excel 进一步分析

用法:
  python export_data.py              # 导出全部（事件 / 每日统计 / 会话）
  python export_data.py events       # 只导事件明细
  python export_data.py daily        # 只导每日统计
  python export_data.py sessions     # 只导在线会话

输出目录: export/（CSV 用 utf-8-sig 编码，Excel 双击直接打开不乱码）
"""

import os
import sys
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BASE_DIR, EVENT_PATH
from utils import read_json
from monitor import Monitor

EXPORT_DIR = os.path.join(BASE_DIR, "export")


def _write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  已导出 {path}（{len(rows)} 行）")


def export_events():
    logs = read_json(EVENT_PATH, [])
    rows = [[e.get("time", ""), e.get("status", ""), e.get("desc1", "")] for e in logs]
    _write_csv(os.path.join(EXPORT_DIR, "events.csv"), ["时间", "状态", "详情"], rows)


def export_daily():
    st = Monitor(log_fn=lambda s: None).compute_stats()
    rows = [[d["date"], d["online_count"], d["sessions"], round(d["minutes"], 1)]
            for d in st.get("daily", [])]
    _write_csv(os.path.join(EXPORT_DIR, "daily.csv"),
               ["日期", "上线次数", "会话数", "在线分钟"], rows)


def export_sessions():
    st = Monitor(log_fn=lambda s: None).compute_stats()
    rows = [[s["start"], s["end"], s["date"], s["hour"], s["duration_minutes"],
             "是" if s.get("ongoing") else ""] for s in st.get("sessions", [])]
    _write_csv(os.path.join(EXPORT_DIR, "sessions.csv"),
               ["开始", "结束", "日期", "小时", "时长(分钟)", "进行中"], rows)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    os.makedirs(EXPORT_DIR, exist_ok=True)
    if which in ("all", "events"):
        export_events()
    if which in ("all", "daily"):
        export_daily()
    if which in ("all", "sessions"):
        export_sessions()
    print(f"导出完成 → {EXPORT_DIR}")


if __name__ == "__main__":
    main()
