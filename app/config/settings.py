import os
import pathlib
import logging
from datetime import datetime, timedelta

# 基础目录设置
BASE_DIR = pathlib.Path(__file__).parent.parent

# 流式响应配置
FAKE_STREAMING = os.environ.get("FAKE_STREAMING", "true").lower() in ["true", "1", "yes"]
# 假流式请求的空内容返回间隔（秒）
FAKE_STREAMING_INTERVAL = float(os.environ.get("FAKE_STREAMING_INTERVAL", "1"))

# 日志配置
logging.getLogger("uvicorn").disabled = True
logging.getLogger("uvicorn.access").disabled = True

# 安全配置
PASSWORD = os.environ.get("PASSWORD", "123").strip('"')
MAX_REQUESTS_PER_MINUTE = int(os.environ.get("MAX_REQUESTS_PER_MINUTE", "30"))
MAX_REQUESTS_PER_DAY_PER_IP = int(os.environ.get("MAX_REQUESTS_PER_DAY_PER_IP", "600"))
RETRY_DELAY = 1
MAX_RETRY_DELAY = 16

# 缓存配置
CACHE_EXPIRY_TIME = int(os.environ.get("CACHE_EXPIRY_TIME", "1200"))  # 默认20分钟
MAX_CACHE_ENTRIES = int(os.environ.get("MAX_CACHE_ENTRIES", "500"))  # 默认最多缓存500条响应
REMOVE_CACHE_AFTER_USE = os.environ.get("REMOVE_CACHE_AFTER_USE", "true").lower() in ["true", "1", "yes"]

# 请求历史配置
REQUEST_HISTORY_EXPIRY_TIME = int(os.environ.get("REQUEST_HISTORY_EXPIRY_TIME", "600"))  # 默认10分钟
ENABLE_RECONNECT_DETECTION = os.environ.get("ENABLE_RECONNECT_DETECTION", "true").lower() in ["true", "1", "yes"]

# 版本信息
local_version = "0.0.0"
remote_version = "0.0.0"
has_update = False

# API调用统计
api_call_stats = {
    'last_24h': {},  # 按小时统计过去24小时
    'hourly': {},    # 按小时统计过去一小时
    'minute': {},    # 按分钟统计过去一分钟
}

# 客户端IP到最近请求的映射，用于识别重连请求
client_request_history = {}