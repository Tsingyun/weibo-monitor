#!/usr/bin/env python3
"""岁己SUI 微博监控 - 主入口"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LOG_PATH, EVENT_PATH, STATS_PATH, HISTORY_PATH
from utils import write_json
from logger import setup_logger

def main():
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

    from monitor import Monitor
    monitor = Monitor(log_fn=logger.info)
    monitor.run()

if __name__ == "__main__":
    main()
