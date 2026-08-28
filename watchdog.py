#!/usr/bin/env python3
"""监控看门狗（A1）— 检测监控进程是否存活，停滞则自动拉起

判定逻辑：
1. 读 data/health.json 的 updated_at，超过阈值（20 倍轮询间隔，且≥5 分钟）视为停滞
2. 同时用 tasklist 校验 PID 是否真的存在（能识别「进程僵死但锁/快照还在」）
3. 需要恢复时：杀掉残留进程 → 清理 monitor.lock → 用 `python -X utf8 app.py` 重新拉起

用法:
  python watchdog.py --check    # 只报告状态，不做任何动作（安全）
  python watchdog.py            # 检查一次，有问题才动作
  python watchdog.py --loop     # 常驻循环检查（每 60 秒），供开机自启使用
"""

import os
import sys
import time
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BASE_DIR, HEALTH_PATH, POLL_INTERVAL
from utils import read_json, beijing_now, beijing_str

LOCK_FILE = os.path.join(BASE_DIR, "data", "monitor.lock")
APP = os.path.join(BASE_DIR, "app.py")
# 停滞阈值：20 倍轮询间隔，且不少于 5 分钟（给足统计刷新等耗时操作的余量）
STALE_SECONDS = max(300, POLL_INTERVAL * 20)
LOOP_INTERVAL = 60


def log(msg):
    print(f"[{beijing_str()}] {msg}", flush=True)


def _pid_alive(pid):
    """Windows：用 tasklist 判断 PID 是否存在"""
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True, timeout=10)
        return str(pid) in (out.stdout or "")
    except Exception:
        return False


def check():
    """返回 (status, detail)，status ∈ running / stale / dead / unknown"""
    h = read_json(HEALTH_PATH, None)

    lock_pid = None
    try:
        with open(LOCK_FILE) as f:
            lock_pid = int(f.read().strip())
    except Exception:
        pass

    if not h:
        # 无健康快照时退化为看锁文件里的 PID（兼容旧版本进程）
        if lock_pid and _pid_alive(lock_pid):
            return "unknown", f"无 health.json，但锁中 PID {lock_pid} 存活（可能是旧版本进程）"
        return "dead", "无 health.json 且无存活进程"

    try:
        upd = datetime.strptime(h["updated_at"], "%Y-%m-%d %H:%M:%S")
        age = (beijing_now() - upd).total_seconds()
    except Exception:
        return "unknown", "health.json 时间字段解析失败"

    pid = h.get("pid")
    if age > STALE_SECONDS:
        alive = bool(pid) and _pid_alive(pid)
        return ("stale" if alive else "dead"), \
               f"心跳停滞 {age:.0f}s（阈值 {STALE_SECONDS}s），PID {pid} 存活={alive}"
    return "running", f"心跳正常（{age:.0f}s 前更新），PID {pid}"


def restart():
    """清理残留进程与锁，然后重新拉起监控"""
    pids = set()
    h = read_json(HEALTH_PATH, None)
    if h and h.get("pid"):
        pids.add(int(h["pid"]))
    try:
        with open(LOCK_FILE) as f:
            pids.add(int(f.read().strip()))
    except Exception:
        pass

    for pid in pids:
        if _pid_alive(pid):
            log(f"终止残留进程 PID {pid}")
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=15)
            except Exception as e:
                log(f"终止 PID {pid} 失败: {e}")

    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            log("已清理 monitor.lock")
    except Exception as e:
        log(f"清锁失败: {e}")

    log("重新启动监控进程…")
    try:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | \
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([sys.executable, "-X", "utf8", APP],
                         cwd=BASE_DIR,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=flags)
        log("监控进程已拉起")
        return True
    except Exception as e:
        log(f"拉起失败: {e}")
        return False


def main():
    args = sys.argv[1:]
    loop = "--loop" in args
    only_check = "--check" in args

    while True:
        status, detail = check()
        log(f"状态={status} · {detail}")
        if only_check:
            return 0
        if status in ("stale", "dead"):
            log("检测到监控未运行，尝试自动恢复…")
            restart()
        if not loop:
            break
        time.sleep(LOOP_INTERVAL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
