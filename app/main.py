from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.models import ErrorResponse
from app.services import GeminiClient
from app.utils import (
    APIKeyManager, 
    test_api_key, 
    format_log_message, 
    log_manager,
    ResponseCacheManager,
    ActiveRequestsManager,
    clean_expired_stats,
    update_api_call_stats
)
from app.api import router, init_router
import os
import json
import asyncio
import requests
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import sys
import pathlib
import random

# 配置环境变量
FAKE_STREAMING = os.environ.get("FAKE_STREAMING", "true").lower() in ["true", "1", "yes"]
# 假流式请求的空内容返回间隔（秒）
FAKE_STREAMING_INTERVAL = float(os.environ.get("FAKE_STREAMING_INTERVAL", "1"))
logging.getLogger("uvicorn").disabled = True
logging.getLogger("uvicorn.access").disabled = True

# 配置 logger
logger = logging.getLogger("my_logger")
logger.setLevel(logging.DEBUG)

# 设置模板目录
BASE_DIR = pathlib.Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI()

# --------------- 全局实例 ---------------

PASSWORD = os.environ.get("PASSWORD", "123").strip('"')
MAX_REQUESTS_PER_MINUTE = int(os.environ.get("MAX_REQUESTS_PER_MINUTE", "30"))
MAX_REQUESTS_PER_DAY_PER_IP = int(
    os.environ.get("MAX_REQUESTS_PER_DAY_PER_IP", "600"))
RETRY_DELAY = 1
MAX_RETRY_DELAY = 16

# 安全设置
safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": 'HARM_CATEGORY_CIVIC_INTEGRITY',
        "threshold": 'BLOCK_NONE'
    }
]

safety_settings_g2 = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "OFF"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "OFF"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "OFF"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "OFF"
    },
    {
        "category": 'HARM_CATEGORY_CIVIC_INTEGRITY',
        "threshold": 'OFF'
    }
]

# 初始化API密钥管理器
key_manager = APIKeyManager()
current_api_key = key_manager.get_available_key()

# 初始化缓存管理器
CACHE_EXPIRY_TIME = int(os.environ.get("CACHE_EXPIRY_TIME", "1200"))  # 默认20分钟
MAX_CACHE_ENTRIES = int(os.environ.get("MAX_CACHE_ENTRIES", "500"))  # 默认最多缓存500条响应
REMOVE_CACHE_AFTER_USE = os.environ.get("REMOVE_CACHE_AFTER_USE", "true").lower() in ["true", "1", "yes"]

# 创建全局缓存字典，将作为缓存管理器的内部存储
response_cache = {}

# 初始化缓存管理器，使用全局字典作为存储
response_cache_manager = ResponseCacheManager(
    expiry_time=CACHE_EXPIRY_TIME,
    max_entries=MAX_CACHE_ENTRIES,
    remove_after_use=REMOVE_CACHE_AFTER_USE,
    cache_dict=response_cache
)

# 活跃请求池 - 将作为活跃请求管理器的内部存储
active_requests_pool = {}

# 初始化活跃请求管理器
active_requests_manager = ActiveRequestsManager(requests_pool=active_requests_pool)

# 添加API调用计数器
api_call_stats = {
    'last_24h': {},  # 按小时统计过去24小时
    'hourly': {},    # 按小时统计过去一小时
    'minute': {},    # 按分钟统计过去一分钟
}

# 客户端IP到最近请求的映射，用于识别重连请求
client_request_history = {}
# 请求历史记录保留时间（秒）
REQUEST_HISTORY_EXPIRY_TIME = int(os.environ.get("REQUEST_HISTORY_EXPIRY_TIME", "600"))  # 默认10分钟
# 是否启用重连检测
ENABLE_RECONNECT_DETECTION = os.environ.get("ENABLE_RECONNECT_DETECTION", "true").lower() in ["true", "1", "yes"]

# 存储版本信息的全局变量
local_version = "0.0.0"
remote_version = "0.0.0"
has_update = False

# --------------- 工具函数 ---------------

def log(level: str, message: str, **extra):
    """简化日志记录的统一函数"""
    msg = format_log_message(level.upper(), message, extra=extra)
    getattr(logger, level.lower())(msg)

def switch_api_key():
    global current_api_key
    key = key_manager.get_available_key() # get_available_key 会处理栈的逻辑
    if key:
        current_api_key = key
        log('info', f"API key 替换为 → {current_api_key[:8]}...", extra={'key': current_api_key[:8], 'request_type': 'switch_key'})
    else:
        log('error', "API key 替换失败，所有API key都已尝试，请重新配置或稍后重试", extra={'key': 'N/A', 'request_type': 'switch_key', 'status_code': 'N/A'})

async def check_keys():
    available_keys = []
    for key in key_manager.api_keys:
        is_valid = await test_api_key(key)
        status_msg = "有效" if is_valid else "无效"
        log('info', f"API Key {key[:10]}... {status_msg}.")
        if is_valid:
            available_keys.append(key)
    if not available_keys:
        log('error', "没有可用的 API 密钥！", extra={'key': 'N/A', 'request_type': 'startup', 'status_code': 'N/A'})
    return available_keys

# 检查版本更新
async def check_version():
    global local_version, remote_version, has_update
    try:
        # 读取本地版本
        with open("version.txt", "r") as f:
            version_line = f.read().strip()
            local_version = version_line.split("=")[1] if "=" in version_line else "0.0.0"
        
        # 获取远程版本
        github_url = "https://raw.githubusercontent.com/wyeeeee/hajimi/refs/heads/main/version.txt"
        response = requests.get(github_url, timeout=5)
        if response.status_code == 200:
            version_line = response.text.strip()
            remote_version = version_line.split("=")[1] if "=" in version_line else "0.0.0"
            
            # 比较版本号
            local_parts = [int(x) for x in local_version.split(".")]
            remote_parts = [int(x) for x in remote_version.split(".")]
            
            # 确保两个列表长度相同
            while len(local_parts) < len(remote_parts):
                local_parts.append(0)
            while len(remote_parts) < len(local_parts):
                remote_parts.append(0)
                
            # 比较版本号
            for i in range(len(local_parts)):
                if remote_parts[i] > local_parts[i]:
                    has_update = True
                    break
                elif remote_parts[i] < local_parts[i]:
                    break
            
            log('info', f"版本检查: 本地版本 {local_version}, 远程版本 {remote_version}, 有更新: {has_update}")
        else:
            log('warning', f"无法获取远程版本信息，HTTP状态码: {response.status_code}")
    except Exception as e:
        log('error', f"版本检查失败: {str(e)}")

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.excepthook(exc_type, exc_value, exc_traceback)
        return
    from app.utils import translate_error
    error_message = translate_error(str(exc_value))
    log('error', f"未捕获的异常: {error_message}", status_code=500, error_message=error_message)

sys.excepthook = handle_exception

# 定期清理缓存的定时任务
def schedule_cache_cleanup():
    scheduler = BackgroundScheduler()
    scheduler.add_job(response_cache_manager.clean_expired, 'interval', minutes=1)  # 每分钟清理过期缓存
    scheduler.add_job(active_requests_manager.clean_completed, 'interval', seconds=30)  # 每30秒清理已完成的活跃请求
    scheduler.add_job(active_requests_manager.clean_long_running, 'interval', minutes=5, args=[300])  # 每5分钟清理运行超过5分钟的任务
    scheduler.add_job(clean_expired_stats, 'interval', minutes=5)  # 每5分钟清理过期的统计数据
    scheduler.start()

# --------------- 事件处理 ---------------

@app.on_event("startup")
async def startup_event():
    log('info', "Starting Gemini API proxy...")
    
    # 启动缓存清理定时任务
    schedule_cache_cleanup()
    
    # 检查版本
    await check_version()
    
    available_keys = await check_keys()
    if available_keys:
        key_manager.api_keys = available_keys
        key_manager._reset_key_stack() # 启动时也确保创建随机栈
        key_manager.show_all_keys()
        log('info', f"可用 API 密钥数量：{len(key_manager.api_keys)}")
        log('info', f"最大重试次数设置为：{len(key_manager.api_keys)}")
        if key_manager.api_keys:
            all_models = await GeminiClient.list_available_models(key_manager.api_keys[0])
            GeminiClient.AVAILABLE_MODELS = [model.replace(
                "models/", "") for model in all_models]
            log('info', "Available models loaded.")
    
    # 初始化路由器
    init_router(
        key_manager,
        response_cache_manager,
        active_requests_manager,
        safety_settings,
        safety_settings_g2,
        current_api_key,
        FAKE_STREAMING,
        FAKE_STREAMING_INTERVAL,
        PASSWORD,
        MAX_REQUESTS_PER_MINUTE,
        MAX_REQUESTS_PER_DAY_PER_IP
    )

# --------------- 异常处理 ---------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from app.utils import translate_error
    error_message = translate_error(str(exc))
    extra_log_unhandled_exception = {'status_code': 500, 'error_message': error_message}
    log('error', f"Unhandled exception: {error_message}", extra=extra_log_unhandled_exception)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=ErrorResponse(message=str(exc), type="internal_error").dict())

# --------------- 路由 ---------------

# 包含API路由
app.include_router(router)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # 先清理过期数据，确保统计数据是最新的
    clean_expired_stats()
    response_cache_manager.clean_expired()  # 使用管理器清理缓存
    active_requests_manager.clean_completed()  # 使用管理器清理活跃请求
    await check_version()
    # 获取当前统计数据
    now = datetime.now()
    
    # 计算过去24小时的调用总数
    last_24h_calls = sum(api_call_stats['last_24h'].values())
    
    # 计算过去一小时内的调用总数
    one_hour_ago = now - timedelta(hours=1)
    hourly_calls = 0
    for hour_key, count in api_call_stats['hourly'].items():
        try:
            hour_time = datetime.strptime(hour_key, '%Y-%m-%d %H:00')
            if hour_time >= one_hour_ago:
                hourly_calls += count
        except ValueError:
            continue
    
    # 计算过去一分钟内的调用总数
    one_minute_ago = now - timedelta(minutes=1)
    minute_calls = 0
    for minute_key, count in api_call_stats['minute'].items():
        try:
            minute_time = datetime.strptime(minute_key, '%Y-%m-%d %H:%M')
            if minute_time >= one_minute_ago:
                minute_calls += count
        except ValueError:
            continue
    
    # 获取最近的日志
    recent_logs = log_manager.get_recent_logs(50)  # 获取最近50条日志
    
    # 获取缓存统计
    total_cache = len(response_cache_manager.cache)
    valid_cache = sum(1 for _, data in response_cache_manager.cache.items() 
                     if time.time() < data.get('expiry_time', 0))
    cache_by_model = {}
    
    # 分析缓存数据
    for _, cache_data in response_cache_manager.cache.items():
        if time.time() < cache_data.get('expiry_time', 0):
            # 按模型统计缓存
            model = cache_data.get('response', {}).model
            if model:
                if model in cache_by_model:
                    cache_by_model[model] += 1
                else:
                    cache_by_model[model] = 1
    
    # 获取请求历史统计
    history_count = len(client_request_history)
    
    # 获取活跃请求统计
    active_count = len(active_requests_manager.active_requests)
    active_done = sum(1 for task in active_requests_manager.active_requests.values() if task.done())
    active_pending = active_count - active_done
    
    # 准备模板上下文
    context = {
        "key_count": len(key_manager.api_keys),
        "model_count": len(GeminiClient.AVAILABLE_MODELS),
        "retry_count": len(key_manager.api_keys),
        "last_24h_calls": last_24h_calls,
        "hourly_calls": hourly_calls,
        "minute_calls": minute_calls,
        "max_requests_per_minute": MAX_REQUESTS_PER_MINUTE,
        "max_requests_per_day_per_ip": MAX_REQUESTS_PER_DAY_PER_IP,
        "current_time": datetime.now().strftime('%H:%M:%S'),
        "logs": recent_logs,
        # 添加版本信息
        "local_version": local_version,
        "remote_version": remote_version,
        "has_update": has_update,
        # 添加缓存信息
        "cache_entries": total_cache,
        "valid_cache": valid_cache,
        "expired_cache": total_cache - valid_cache,
        "cache_expiry_time": CACHE_EXPIRY_TIME,
        "max_cache_entries": MAX_CACHE_ENTRIES,
        "cache_by_model": cache_by_model,
        "request_history_count": history_count,
        "enable_reconnect_detection": ENABLE_RECONNECT_DETECTION,
        "remove_cache_after_use": REMOVE_CACHE_AFTER_USE,
        # 添加活跃请求池信息
        "active_count": active_count,
        "active_done": active_done,
        "active_pending": active_pending,
    }
    
    # 使用Jinja2模板引擎正确渲染HTML
    return templates.TemplateResponse("index.html", {"request": request, **context})