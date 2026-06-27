"""日志模块 - RotatingFileHandler + 终端输出"""

import logging
from logging.handlers import RotatingFileHandler
from config import LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

def setup_logger(name="weibo-monitor"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # 终端 Handler
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(console)

    # 文件 Handler（轮转）
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(file_handler)

    return logger
