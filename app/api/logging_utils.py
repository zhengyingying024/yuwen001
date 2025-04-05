import logging
from app.utils import format_log_message

# 获取logger
logger = logging.getLogger("my_logger")

# 日志记录函数
def log(level: str, message: str, **extra):
    """简化日志记录的统一函数"""
    msg = format_log_message(level.upper(), message, extra=extra)
    getattr(logger, level.lower())(msg)