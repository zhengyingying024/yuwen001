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
    update_api_call_stats,
    check_version,
    schedule_cache_cleanup,
    handle_exception,
    log
)
from app.api import router, init_router, dashboard_router, init_dashboard_router
from app.config.settings import (
    FAKE_STREAMING,
    FAKE_STREAMING_INTERVAL,
    RANDOM_STRING,
    RANDOM_STRING_LENGTH,
    PASSWORD,
    MAX_REQUESTS_PER_MINUTE,
    MAX_REQUESTS_PER_DAY_PER_IP,
    RETRY_DELAY,
    MAX_RETRY_DELAY,
    CACHE_EXPIRY_TIME,
    MAX_CACHE_ENTRIES,
    REMOVE_CACHE_AFTER_USE,
    REQUEST_HISTORY_EXPIRY_TIME,
    ENABLE_RECONNECT_DETECTION,
    api_call_stats,
    client_request_history,
    version,
    API_KEY_DAILY_LIMIT
)
from app.config.safety import SAFETY_SETTINGS, SAFETY_SETTINGS_G2
import os
import json
import asyncio
import time
import logging
from datetime import datetime, timedelta
import sys
import pathlib

# 设置模板目录
BASE_DIR = pathlib.Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(limit="50M")

# --------------- 全局实例 ---------------

# 初始化API密钥管理器
key_manager = APIKeyManager()
current_api_key = key_manager.get_available_key()

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

# --------------- 工具函数 ---------------

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

# 设置全局异常处理
sys.excepthook = handle_exception

# --------------- 事件处理 ---------------

@app.on_event("startup")
async def startup_event():
    log('info', "Starting Gemini API proxy...")
    
    # 启动缓存清理定时任务
    schedule_cache_cleanup(response_cache_manager, active_requests_manager)
    
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
        SAFETY_SETTINGS,
        SAFETY_SETTINGS_G2,
        current_api_key,
        FAKE_STREAMING,
        FAKE_STREAMING_INTERVAL,
        PASSWORD,
        MAX_REQUESTS_PER_MINUTE,
        MAX_REQUESTS_PER_DAY_PER_IP
    )
    
    # 初始化仪表盘路由器
    init_dashboard_router(
        key_manager,
        response_cache_manager,
        active_requests_manager
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
app.include_router(dashboard_router)

# 挂载静态文件目录
app.mount("/assets", StaticFiles(directory="app/templates/assets"), name="assets")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    根路由 - 返回静态 HTML 文件
    """
    # 直接返回 index.html 文件
    return templates.TemplateResponse("index.html", {"request": request})