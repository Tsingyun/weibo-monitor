#!/usr/bin/env python3
"""岁己SUI 微博监控 - 主入口"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import LOG_PATH, STATS_PATH, HISTORY_PATH
from utils import read_json, write_json, beijing_str, beijing_now
from logger import setup_logger

def main():
    # 确保数据目录和必要文件存在
    for path in [LOG_PATH, STATS_PATH]:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
    if not os.path.exists(HISTORY_PATH):
        write_json(HISTORY_PATH, [])
    if not os.path.exists(LOG_PATH):
        write_json(os.path.dirname(LOG_PATH) + "/weibolog.json", [])

    # 启动日志
    logger = setup_logger()
    logger.info("岁己SUI 微博监控系统启动")

    from monitor import Monitor
    monitor = Monitor(log_fn=logger.info)
    monitor.run()

if __name__ == "__main__":
    main()
