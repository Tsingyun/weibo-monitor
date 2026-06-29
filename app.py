#!/usr/bin/env python3
"""岁己SUI 微博监控 - 主入口（含进程互斥锁）"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LOG_PATH, EVENT_PATH, STATS_PATH, HISTORY_PATH
from utils import write_json
from logger import setup_logger

LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "monitor.lock")

def acquire_lock():
    """获取进程互斥锁，防止重复启动"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                old_pid = int(f.read().strip())
            # 检查旧进程是否仍在运行
            try:
                os.kill(old_pid, 0)  # 信号 0 不杀死进程，仅检测存在
                print(f"❌ 监控已在运行中 (PID: {old_pid})")
                print("   如需重启，请先关闭现有实例")
                return False
            except (OSError, ProcessLookupError):
                # 旧进程已退出，锁文件是残留的
                os.remove(LOCK_FILE)
        except (ValueError, OSError):
            os.remove(LOCK_FILE)

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def release_lock():
    """释放进程锁"""
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass

def main():
    # 进程互斥
    if not acquire_lock():
        sys.exit(1)

    # 确保目录和必要文件存在
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(EVENT_PATH), exist_ok=True)
    if not os.path.exists(EVENT_PATH):
        write_json(EVENT_PATH, [])
    if not os.path.exists(HISTORY_PATH):
        write_json(HISTORY_PATH, [])

    # 启动日志
    logger = setup_logger()
    logger.info("岁己SUI 微博监控系统启动")

    try:
        from monitor import Monitor
        monitor = Monitor(log_fn=logger.info)
        monitor.run()
    except KeyboardInterrupt:
        pass
    finally:
        release_lock()

if __name__ == "__main__":
    main()
