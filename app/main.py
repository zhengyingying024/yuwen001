from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .models import ChatCompletionRequest, ChatCompletionResponse, ErrorResponse, ModelList
from .gemini import GeminiClient, ResponseWrapper
from .utils import handle_gemini_error, protect_from_abuse, APIKeyManager, test_api_key, format_log_message, log_manager
import os
import json
import asyncio
from typing import Literal, Dict, Any, Optional
import random
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import sys
import logging
from collections import defaultdict
import pathlib
import hashlib
import time

logging.getLogger("uvicorn").disabled = True
logging.getLogger("uvicorn.access").disabled = True

# 配置 logger
logger = logging.getLogger("my_logger")
logger.setLevel(logging.DEBUG)

# 设置模板目录
BASE_DIR = pathlib.Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR))

app = FastAPI()

# --------------- 缓存管理类 ---------------

class ResponseCacheManager:
    """管理API响应缓存的类"""
    
    def __init__(self, expiry_time: int, max_entries: int, remove_after_use: bool = True, 
                cache_dict: Dict[str, Dict[str, Any]] = None):
        self.cache = cache_dict if cache_dict is not None else {}  # 使用传入的缓存字典或创建新字典
        self.expiry_time = expiry_time
        self.max_entries = max_entries
        self.remove_after_use = remove_after_use
    
    def get(self, cache_key: str):
        """获取缓存项，如果存在且未过期"""
        now = time.time()
        if cache_key in self.cache and now < self.cache[cache_key].get('expiry_time', 0):
            cached_item = self.cache[cache_key]
            
            # 获取响应但先不删除
            response = cached_item['response']
            
            # 返回响应
            return response, True
        
        return None, False
    
    def store(self, cache_key: str, response, client_ip: str = None):
        """存储响应到缓存"""
        now = time.time()
        self.cache[cache_key] = {
            'response': response,
            'expiry_time': now + self.expiry_time,
            'created_at': now,
            'client_ip': client_ip
        }
        
        log('info', f"响应已缓存: {cache_key[:8]}...", 
            extra={'cache_operation': 'store', 'request_type': 'non-stream'})
        
        # 如果缓存超过限制，清理最旧的
        self.clean_if_needed()
    
    def clean_expired(self):
        """清理所有过期的缓存项"""
        now = time.time()
        expired_keys = [k for k, v in self.cache.items() if now > v.get('expiry_time', 0)]
        
        for key in expired_keys:
            del self.cache[key]
            log('info', f"清理过期缓存: {key[:8]}...", extra={'cache_operation': 'clean'})
    
    def clean_if_needed(self):
        """如果缓存数量超过限制，清理最旧的项目"""
        if len(self.cache) <= self.max_entries:
            return
        
        # 按创建时间排序
        sorted_keys = sorted(self.cache.keys(),
                           key=lambda k: self.cache[k].get('created_at', 0))
        
        # 计算需要删除的数量
        to_remove = len(self.cache) - self.max_entries
        
        # 删除最旧的项
        for key in sorted_keys[:to_remove]:
            del self.cache[key]
            log('info', f"缓存容量限制，删除旧缓存: {key[:8]}...", extra={'cache_operation': 'limit'})

# --------------- 活跃请求管理类 ---------------

class ActiveRequestsManager:
    """管理活跃API请求的类"""
    
    def __init__(self, requests_pool: Dict[str, asyncio.Task] = None):
        self.active_requests = requests_pool if requests_pool is not None else {}  # 存储活跃请求
    
    def add(self, key: str, task: asyncio.Task):
        """添加新的活跃请求任务"""
        task.creation_time = time.time()  # 添加创建时间属性
        self.active_requests[key] = task
    
    def get(self, key: str):
        """获取活跃请求任务"""
        return self.active_requests.get(key)
    
    def remove(self, key: str):
        """移除活跃请求任务"""
        if key in self.active_requests:
            del self.active_requests[key]
            return True
        return False
    
    def remove_by_prefix(self, prefix: str):
        """移除所有以特定前缀开头的活跃请求任务"""
        keys_to_remove = [k for k in self.active_requests.keys() if k.startswith(prefix)]
        for key in keys_to_remove:
            self.remove(key)
        return len(keys_to_remove)
    
    def clean_completed(self):
        """清理所有已完成或已取消的任务"""
        keys_to_remove = []
        
        for key, task in self.active_requests.items():
            if task.done() or task.cancelled():
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            self.remove(key)
        
        # if keys_to_remove:
        #    log('info', f"清理已完成请求任务: {len(keys_to_remove)}个", cleanup='active_requests')
    
    def clean_long_running(self, max_age_seconds: int = 300):
        """清理长时间运行的任务"""
        now = time.time()
        long_running_keys = []
        
        for key, task in list(self.active_requests.items()):
            if (hasattr(task, 'creation_time') and
                task.creation_time < now - max_age_seconds and
                not task.done() and not task.cancelled()):
                
                long_running_keys.append(key)
                task.cancel()  # 取消长时间运行的任务
        
        if long_running_keys:
            log('warning', f"取消长时间运行的任务: {len(long_running_keys)}个", cleanup='long_running_tasks')



# --------------- 全局实例 ---------------

PASSWORD = os.environ.get("PASSWORD", "123").strip('"')
MAX_REQUESTS_PER_MINUTE = int(os.environ.get("MAX_REQUESTS_PER_MINUTE", "30"))
MAX_REQUESTS_PER_DAY_PER_IP = int(
    os.environ.get("MAX_REQUESTS_PER_DAY_PER_IP", "600"))
# MAX_RETRIES = int(os.environ.get('MaxRetries', '3').strip() or '3')
RETRY_DELAY = 1
MAX_RETRY_DELAY = 16
MAX_RETRY_DELAY = 16
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

key_manager = APIKeyManager() # 实例化 APIKeyManager，栈会在 __init__ 中初始化
current_api_key = key_manager.get_available_key()

# 初始化缓存管理器
CACHE_EXPIRY_TIME = int(os.environ.get("CACHE_EXPIRY_TIME", "1200"))  # 默认20分钟
MAX_CACHE_ENTRIES = int(os.environ.get("MAX_CACHE_ENTRIES", "500"))  # 默认最多缓存500条响应
REMOVE_CACHE_AFTER_USE = os.environ.get("REMOVE_CACHE_AFTER_USE", "true").lower() in ["true", "1", "yes"]

# 创建全局缓存字典，将作为缓存管理器的内部存储
# 注意：所有缓存操作都应通过 response_cache_manager 进行，不要直接操作此字典
response_cache: Dict[str, Dict[str, Any]] = {}

# 初始化缓存管理器，使用全局字典作为存储
response_cache_manager = ResponseCacheManager(
    expiry_time=CACHE_EXPIRY_TIME,
    max_entries=MAX_CACHE_ENTRIES,
    remove_after_use=REMOVE_CACHE_AFTER_USE,
    cache_dict=response_cache  # 使用同一个字典实例，确保统一
)

# 活跃请求池 - 将作为活跃请求管理器的内部存储
# 注意：所有活跃请求操作都应通过 active_requests_manager 进行，不要直接操作此字典
active_requests_pool: Dict[str, asyncio.Task] = {}

# 初始化活跃请求管理器
active_requests_manager = ActiveRequestsManager(requests_pool=active_requests_pool)

# 添加API调用计数器
api_call_stats = {
    'last_24h': defaultdict(int),  # 按小时统计过去24小时
    'hourly': defaultdict(int),    # 按小时统计过去一小时
    'minute': defaultdict(int),    # 按分钟统计过去一分钟
}

# 清理过期统计数据的函数
def clean_expired_stats():
    now = datetime.now()
    
    # 清理24小时前的数据
    for hour_key in list(api_call_stats['last_24h'].keys()):
        try:
            hour_time = datetime.strptime(hour_key, '%Y-%m-%d %H:00')
            if (now - hour_time).total_seconds() > 24 * 3600:  # 超过24小时
                del api_call_stats['last_24h'][hour_key]
        except ValueError:
            # 如果键格式不正确，直接删除
            del api_call_stats['last_24h'][hour_key]
    
    # 清理一小时前的小时统计数据
    one_hour_ago = now - timedelta(hours=1)
    for hour_key in list(api_call_stats['hourly'].keys()):
        try:
            hour_time = datetime.strptime(hour_key, '%Y-%m-%d %H:00')
            if hour_time < one_hour_ago:
                del api_call_stats['hourly'][hour_key]
        except ValueError:
            # 如果键格式不正确，直接删除
            del api_call_stats['hourly'][hour_key]
    
    # 清理一分钟前的分钟统计数据
    one_minute_ago = now - timedelta(minutes=1)
    for minute_key in list(api_call_stats['minute'].keys()):
        try:
            minute_time = datetime.strptime(minute_key, '%Y-%m-%d %H:%M')
            if minute_time < one_minute_ago:
                del api_call_stats['minute'][minute_key]
        except ValueError:
            # 如果键格式不正确，直接删除
            del api_call_stats['minute'][minute_key]

# 更新API调用统计的函数
def update_api_call_stats():
    now = datetime.now()
    hour_key = now.strftime('%Y-%m-%d %H:00')
    minute_key = now.strftime('%Y-%m-%d %H:%M')
    
    # 检查并清理过期统计
    clean_expired_stats()
    
    # 更新统计
    api_call_stats['last_24h'][hour_key] += 1
    api_call_stats['hourly'][hour_key] += 1
    api_call_stats['minute'][minute_key] += 1
    
    log('info', "API调用统计已更新: 24小时=%s, 1小时=%s, 1分钟=%s" % (sum(api_call_stats['last_24h'].values()), sum(api_call_stats['hourly'].values()), sum(api_call_stats['minute'].values())))


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


# 存储版本信息的全局变量
local_version = "0.0.0"
remote_version = "0.0.0"
has_update = False

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


# --------------- 工具函数 ---------------

def log(level: str, message: str, **extra):
    """简化日志记录的统一函数"""
    msg = format_log_message(level.upper(), message, extra=extra)
    getattr(logger, level.lower())(msg)

def translate_error(message: str) -> str:
    if "quota exceeded" in message.lower():
        return "API 密钥配额已用尽"
    if "invalid argument" in message.lower():
        return "无效参数"
    if "internal server error" in message.lower():
        return "服务器内部错误"
    if "service unavailable" in message.lower():
        return "服务不可用"
    return message

def create_chat_response(model: str, choices: list, id: str = None) -> ChatCompletionResponse:
    """创建标准响应对象的工厂函数"""
    return ChatCompletionResponse(
        id=id or f"chatcmpl-{int(time.time()*1000)}",
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=choices
    )

def create_error_response(model: str, error_message: str) -> ChatCompletionResponse:
    """创建错误响应对象的工厂函数"""
    return create_chat_response(
        model=model,
        choices=[{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": error_message
            },
            "finish_reason": "error"
        }]
    )

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.excepthook(exc_type, exc_value, exc_traceback)
        return
    error_message = translate_error(str(exc_value))
    log('error', f"未捕获的异常: {error_message}", status_code=500, error_message=error_message)

sys.excepthook = handle_exception

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
        # MAX_RETRIES = len(key_manager.api_keys)
        log('info', f"最大重试次数设置为：{len(key_manager.api_keys)}") # 添加日志
        if key_manager.api_keys:
            all_models = await GeminiClient.list_available_models(key_manager.api_keys[0])
            GeminiClient.AVAILABLE_MODELS = [model.replace(
                "models/", "") for model in all_models]
            log('info', "Available models loaded.")

@app.get("/v1/models", response_model=ModelList)
def list_models():
    log('info', "Received request to list models", extra={'request_type': 'list_models', 'status_code': 200})
    return ModelList(data=[{"id": model, "object": "model", "created": 1678888888, "owned_by": "organization-owner"} for model in GeminiClient.AVAILABLE_MODELS])


async def verify_password(request: Request):
    if PASSWORD:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401, detail="Unauthorized: Missing or invalid token")
        token = auth_header.split(" ")[1]
        if token != PASSWORD:
            raise HTTPException(
                status_code=401, detail="Unauthorized: Invalid token")


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest, http_request: Request, _: None = Depends(verify_password)):
    # 获取客户端IP
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    # 流式请求直接处理，不使用缓存
    if request.stream:
        return await process_request(request, http_request, "stream")
    
    # 生成完整缓存键 - 用于精确匹配
    cache_key = generate_cache_key(request)
    
    # 记录请求缓存键信息
    log('info', f"请求缓存键: {cache_key[:8]}...", 
        extra={'cache_key': cache_key[:8], 'request_type': 'non-stream'})
    
    # 检查精确缓存是否存在且未过期
    cached_response, cache_hit = response_cache_manager.get(cache_key)
    if cache_hit:
        # 精确缓存命中
        log('info', f"精确缓存命中: {cache_key[:8]}...", 
            extra={'cache_operation': 'hit', 'request_type': 'non-stream'})
        
        # 同时清理相关的活跃任务，避免后续请求等待已经不需要的任务
        active_requests_manager.remove_by_prefix(f"cache:{cache_key}")
        
        # 安全删除缓存
        if cache_key in response_cache_manager.cache:
            del response_cache_manager.cache[cache_key]
            log('info', f"缓存使用后已删除: {cache_key[:8]}...", 
                extra={'cache_operation': 'used-and-removed', 'request_type': 'non-stream'})
        
        # 返回缓存响应
        return cached_response
    
    # 构建包含缓存键的活跃请求池键
    pool_key = f"cache:{cache_key}"
    
    # 查找所有使用相同缓存键的活跃任务
    active_task = active_requests_manager.get(pool_key)
    if active_task and not active_task.done():
        log('info', f"发现相同请求的进行中任务", 
            extra={'request_type': 'non-stream', 'model': request.model})
        
        # 等待已有任务完成
        try:
            # 设置超时，避免无限等待
            await asyncio.wait_for(active_task, timeout=180)
            
            # 通过缓存管理器获取已完成任务的结果
            cached_response, cache_hit = response_cache_manager.get(cache_key)
            if cache_hit:
                # 安全删除缓存
                if cache_key in response_cache_manager.cache:
                    del response_cache_manager.cache[cache_key]
                    log('info', f"使用已完成任务的缓存后删除: {cache_key[:8]}...", 
                        extra={'cache_operation': 'used-and-removed', 'request_type': 'non-stream'})
                
                return cached_response
                
            # 如果缓存已被清除或不存在，使用任务结果
            if active_task.done() and not active_task.cancelled():
                result = active_task.result()
                if result:
                    # log('info', f"使用已完成任务的原始结果", 
                    #     extra={'request_type': 'non-stream', 'model': request.model})
                    
                    # 使用原始结果时，我们需要创建一个新的响应对象
                    # 避免使用可能已被其他请求修改的对象
                    new_response = ChatCompletionResponse(
                        id=f"chatcmpl-{int(time.time()*1000)}",
                        object="chat.completion", 
                        created=int(time.time()),
                        model=result.model,
                        choices=result.choices
                    )
                    
                    # 不要缓存此结果，因为它很可能是一个已存在但被使用后清除的缓存
                    return new_response
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            # 任务超时或被取消的情况下，记录日志然后让代码继续执行
            error_type = "超时" if isinstance(e, asyncio.TimeoutError) else "被取消"
            log('warning', f"等待已有任务{error_type}: {pool_key}", 
                extra={'request_type': 'non-stream', 'model': request.model})
            
            # 从活跃请求池移除该任务
            if active_task.done() or active_task.cancelled():
                active_requests_manager.remove(pool_key)
                log('info', f"已从活跃请求池移除{error_type}任务: {pool_key}", 
                    extra={'request_type': 'non-stream'})
     
    # 创建请求处理任务
    process_task = asyncio.create_task(
        process_request(request, http_request, "non-stream", cache_key=cache_key, client_ip=client_ip)
    )
    
    # 将任务添加到活跃请求池
    active_requests_manager.add(pool_key, process_task)
    
    # 等待任务完成
    try:
        response = await process_task
        return response
    except Exception as e:
        # 如果任务失败，从活跃请求池中移除
        active_requests_manager.remove(pool_key)
        
        # 检查是否已有缓存的结果（可能是由另一个任务创建的）
        cached_response, cache_hit = response_cache_manager.get(cache_key)
        if cache_hit:
            log('info', f"任务失败但找到缓存，使用缓存结果: {cache_key[:8]}...", 
                extra={'request_type': 'non-stream', 'model': request.model})
            return cached_response
        
        # 重新抛出异常
        raise

async def process_request(chat_request: ChatCompletionRequest, http_request: Request, request_type: Literal['stream', 'non-stream'], cache_key: str = None, client_ip: str = None):
    """处理API请求的主函数，根据需要处理流式或非流式请求"""
    global current_api_key
    
    # 请求前基本检查
    protect_from_abuse(
        http_request, MAX_REQUESTS_PER_MINUTE, MAX_REQUESTS_PER_DAY_PER_IP)
    if chat_request.model not in GeminiClient.AVAILABLE_MODELS:
        error_msg = "无效的模型"
        extra_log = {'request_type': request_type, 'model': chat_request.model, 'status_code': 400, 'error_message': error_msg}
        log('error', error_msg, extra=extra_log)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # 重置已尝试的密钥
    key_manager.reset_tried_keys_for_request()
    
    # 转换消息格式
    contents, system_instruction = GeminiClient.convert_messages(
        GeminiClient, chat_request.messages)

    # 设置重试次数（使用可用API密钥数量作为最大重试次数）
    retry_attempts = len(key_manager.api_keys) if key_manager.api_keys else 1
    
    # 尝试使用不同API密钥
    for attempt in range(1, retry_attempts + 1):
        # 获取下一个密钥
        current_api_key = key_manager.get_available_key()
        
        # 检查API密钥是否可用
        if current_api_key is None:
            log('warning', "没有可用的 API 密钥，跳过本次尝试", 
                extra={'request_type': request_type, 'model': chat_request.model, 'status_code': 'N/A'})
            break
        
        # 记录当前尝试的密钥信息
        log('info', f"第 {attempt}/{retry_attempts} 次尝试 ... 使用密钥: {current_api_key[:8]}...", 
            extra={'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model})

        # 服务器错误重试逻辑
        server_error_retries = 3
        for server_retry in range(1, server_error_retries + 1):
            try:
                # 根据请求类型分别处理
                if chat_request.stream:
                    return await process_stream_request(
                        chat_request, 
                        http_request, 
                        contents, 
                        system_instruction, 
                        current_api_key
                    )
                else:
                    return await process_nonstream_request(
                        chat_request,
                        http_request,
                        request_type,
                        contents,
                        system_instruction,
                        current_api_key,
                        cache_key,
                        client_ip
                    )
            except HTTPException as e:
                if e.status_code == status.HTTP_408_REQUEST_TIMEOUT:
                    log('error', "客户端连接中断", 
                        extra={'key': current_api_key[:8], 'request_type': request_type, 
                              'model': chat_request.model, 'status_code': 408})
                    raise
                else:
                    raise
            except Exception as e:
                # 使用统一的API错误处理函数
                error_result = await handle_api_error(
                    e, 
                    current_api_key, 
                    key_manager, 
                    request_type, 
                    chat_request.model, 
                    server_retry - 1
                )
                
                # 如果需要删除缓存，清除缓存
                if error_result.get('remove_cache', False) and cache_key and cache_key in response_cache_manager.cache:
                    log('info', f"因API错误，删除缓存: {cache_key[:8]}...", 
                        extra={'cache_operation': 'remove-on-error', 'request_type': request_type})
                    del response_cache_manager.cache[cache_key]
                
                if error_result.get('should_retry', False):
                    # 服务器错误需要重试（等待已在handle_api_error中完成）
                    continue
                elif error_result.get('should_switch_key', False) and attempt < retry_attempts:
                    # 跳出服务器错误重试循环，获取下一个可用密钥
                    log('info', f"API密钥 {current_api_key[:8]}... 失败，准备尝试下一个密钥", 
                        extra={'key': current_api_key[:8], 'request_type': request_type})
                    break  
                else:
                    # 无法处理的错误或已达到重试上限
                    break

    # 如果所有尝试都失败
    msg = "所有API密钥均请求失败,请稍后重试"
    log('error', "API key 替换失败，所有API key都已尝试，请重新配置或稍后重试", extra={'key': 'N/A', 'request_type': 'switch_key', 'status_code': 'N/A'})
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_message = translate_error(str(exc))
    extra_log_unhandled_exception = {'status_code': 500, 'error_message': error_message}
    log('error', f"Unhandled exception: {error_message}", extra=extra_log_unhandled_exception)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=ErrorResponse(message=str(exc), type="internal_error").dict())


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

# 客户端IP到最近请求的映射，用于识别重连请求
client_request_history: Dict[str, Dict[str, Any]] = {}
# 请求历史记录保留时间（秒）
REQUEST_HISTORY_EXPIRY_TIME = int(os.environ.get("REQUEST_HISTORY_EXPIRY_TIME", "600"))  # 默认10分钟
# 是否启用重连检测
ENABLE_RECONNECT_DETECTION = os.environ.get("ENABLE_RECONNECT_DETECTION", "true").lower() in ["true", "1", "yes"]

# 定期清理缓存的定时任务
def schedule_cache_cleanup():
    scheduler = BackgroundScheduler()
    scheduler.add_job(response_cache_manager.clean_expired, 'interval', minutes=1)  # 每分钟清理过期缓存
    scheduler.add_job(active_requests_manager.clean_completed, 'interval', seconds=30)  # 每30秒清理已完成的活跃请求
    scheduler.add_job(active_requests_manager.clean_long_running, 'interval', minutes=5, args=[300])  # 每5分钟清理运行超过5分钟的任务
    scheduler.add_job(clean_expired_stats, 'interval', minutes=5)  # 每5分钟清理过期的统计数据
    scheduler.start()

# 生成请求的唯一缓存键
def generate_cache_key(chat_request: ChatCompletionRequest) -> str:
    # 创建包含请求关键信息的字典
    request_data = {
        'model': chat_request.model, 
        'messages': []
    }
    
    # 添加消息内容
    for msg in chat_request.messages:
        if isinstance(msg.content, str):
            message_data = {'role': msg.role, 'content': msg.content}
            request_data['messages'].append(message_data)
        elif isinstance(msg.content, list):
            content_list = []
            for item in msg.content:
                if item.get('type') == 'text':
                    content_list.append({'type': 'text', 'text': item.get('text')})
                # 对于图像数据，我们只使用标识符而不是全部数据
                elif item.get('type') == 'image_url':
                    image_data = item.get('image_url', {}).get('url', '')
                    if image_data.startswith('data:image/'):
                        # 对于base64图像，使用前32字符作为标识符
                        content_list.append({'type': 'image_url', 'hash': hashlib.md5(image_data[:32].encode()).hexdigest()})
                    else:
                        content_list.append({'type': 'image_url', 'url': image_data})
            request_data['messages'].append({'role': msg.role, 'content': content_list})
    
    # 将字典转换为JSON字符串并计算哈希值
    json_data = json.dumps(request_data, sort_keys=True)
    return hashlib.md5(json_data.encode()).hexdigest()

# 拆分process_request为更小的函数

async def process_stream_request(
    chat_request: ChatCompletionRequest,
    http_request: Request,
    contents,
    system_instruction,
    current_api_key: str
) -> StreamingResponse:
    """处理流式API请求"""
    gemini_client = GeminiClient(current_api_key)
    
    async def stream_generator():
        try:
            # 标记是否成功获取到响应
            success = False
            async for chunk in gemini_client.stream_chat(
                chat_request,
                contents,
                safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings,
                system_instruction
            ):
                # 空字符串跳过
                if not chunk:
                    continue
                    
                formatted_chunk = {
                    "id": "chatcmpl-someid",
                    "object": "chat.completion.chunk",
                    "created": 1234567,
                    "model": chat_request.model,
                    "choices": [{"delta": {"role": "assistant", "content": chunk}, "index": 0, "finish_reason": None}]
                }
                success = True  # 只要有一个chunk成功，就标记为成功
                yield f"data: {json.dumps(formatted_chunk)}\n\n"
            
            # 如果成功获取到响应，更新API调用统计
            if success:
                update_api_call_stats()
                
            yield "data: [DONE]\n\n"

        except asyncio.CancelledError:
            extra_log_cancel = {'key': current_api_key[:8], 'request_type': 'stream', 'model': chat_request.model, 'error_message': '客户端已断开连接'}
            log('info', "客户端连接已中断", extra=extra_log_cancel)
        except Exception as e:
            error_detail = handle_gemini_error(e, current_api_key, key_manager)
            yield f"data: {json.dumps({'error': {'message': error_detail, 'type': 'gemini_error'}})}\n\n"
            
    return StreamingResponse(stream_generator(), media_type="text/event-stream")

async def run_gemini_completion(
    gemini_client, 
    chat_request: ChatCompletionRequest, 
    contents,
    system_instruction,
    request_type: str,
    current_api_key: str
):
    """运行Gemini非流式请求"""
    # 记录函数调用状态
    run_fn = run_gemini_completion
    
    try:
        # 创建一个不会被客户端断开影响的任务
        response_future = asyncio.create_task(
            asyncio.to_thread(
                gemini_client.complete_chat, 
                chat_request, 
                contents, 
                safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings, 
                system_instruction
            )
        )
        
        # 使用shield防止任务被外部取消
        response_content = await asyncio.shield(response_future)
        
        # 只在第一次调用时记录完成日志
        if not hasattr(run_fn, 'logged_complete'):
            log('info', "非流式请求成功完成", extra={'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model})
            run_fn.logged_complete = True
        return response_content
    except asyncio.CancelledError:
        # 即使任务被取消，我们也确保正在进行的API请求能够完成
        if 'response_future' in locals() and not response_future.done():
            try:
                # 使用shield确保任务不被取消，并等待它完成
                response_content = await asyncio.shield(response_future)
                log('info', "API请求在客户端断开后完成", extra={'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model})
                return response_content
            except Exception as e:
                extra_log_gemini_cancel = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message': f'API请求在客户端断开后失败: {str(e)}'}
                log('info', "API调用因客户端断开而失败", extra=extra_log_gemini_cancel)
                raise
        
        # 如果任务尚未开始或已经失败，记录日志
        extra_log_gemini_cancel = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message': '客户端断开导致API调用取消'}
        log('info', "API调用因客户端断开而取消", extra=extra_log_gemini_cancel)
        raise

async def check_client_disconnect(http_request: Request, current_api_key: str, request_type: str, model: str):
    """检查客户端是否断开连接"""
    while True:
        if await http_request.is_disconnected():
            extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': model, 'error_message': '检测到客户端断开连接'}
            log('info', "客户端连接已中断，等待API请求完成", extra=extra_log)
            return True
        await asyncio.sleep(0.5)

async def handle_client_disconnect(
    gemini_task: asyncio.Task, 
    chat_request: ChatCompletionRequest, 
    request_type: str, 
    current_api_key: str,
    cache_key: str = None,
    client_ip: str = None
):

    try:
        # 等待API任务完成，使用shield防止它被取消
        response_content = await asyncio.shield(gemini_task)
        
        # 检查响应文本是否为空
        if response_content is None or response_content.text == "":
            if response_content is None:
                log('info', "客户端断开后API任务返回None", 
                    extra={'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model})
            else:
                extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'status_code': 204}
                log('info', "客户端断开后Gemini API 返回空响应", extra=extra_log)
            
            # 删除任何现有缓存，因为响应为空
            if cache_key and cache_key in response_cache_manager.cache:
                log('info', f"因空响应，删除缓存: {cache_key[:8]}...", 
                    extra={'cache_operation': 'remove-on-empty', 'request_type': request_type})
                del response_cache_manager.cache[cache_key]
                
            # 返回错误响应而不是None
            return create_error_response(chat_request.model, "AI未返回任何内容，请重试")
        
        # 首先检查是否有现有缓存
        cached_response, cache_hit = response_cache_manager.get(cache_key)
        if cache_hit:
            log('info', f"客户端断开但找到已存在缓存，将删除: {cache_key[:8]}...", 
                extra={'cache_operation': 'disconnect-found-cache', 'request_type': request_type})
            
            # 安全删除缓存
            if cache_key in response_cache_manager.cache:
                del response_cache_manager.cache[cache_key]
            
            # 不返回缓存，而是创建新响应并缓存
        
        # 创建新响应
        # log('info', f"客户端断开后创建新缓存: {cache_key[:8] if cache_key else 'none'}...", 
        #     extra={'cache_operation': 'create-after-disconnect', 'request_type': request_type})
        response = create_response(chat_request, response_content)
        
        # 客户端已断开，此响应不会实际发送，可以考虑将其缓存以供后续使用
        # 如果确实需要缓存，则可以取消下面的注释
        # cache_response(response, cache_key, client_ip)
        
        return response
    except asyncio.CancelledError:
        # 对于取消异常，仍然尝试继续完成任务
        log('info', "客户端断开后任务被取消，但我们仍会尝试完成", 
            extra={'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model})
        
        # 检查任务是否已经完成
        if gemini_task.done() and not gemini_task.cancelled():
            try:
                response_content = gemini_task.result()
                
                # 首先检查是否有现有缓存
                cached_response, cache_hit = response_cache_manager.get(cache_key)
                if cache_hit:
                    log('info', f"任务被取消但找到已存在缓存，将删除: {cache_key[:8]}...", 
                        extra={'cache_operation': 'cancel-found-cache', 'request_type': request_type})
                    
                    # 安全删除缓存
                    if cache_key in response_cache_manager.cache:
                        del response_cache_manager.cache[cache_key]
                
                # 创建但不缓存响应
                response = create_response(chat_request, response_content)
                return response
            except Exception as inner_e:
                log('error', f"客户端断开后从已完成任务获取结果失败: {str(inner_e)}", 
                    extra={'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model})
                
                # 删除缓存，因为出现错误
                if cache_key and cache_key in response_cache_manager.cache:
                    log('info', f"因任务获取结果失败，删除缓存: {cache_key[:8]}...", 
                        extra={'cache_operation': 'remove-on-error', 'request_type': request_type})
                    del response_cache_manager.cache[cache_key]
        
        # 创建错误响应而不是返回None
        return create_error_response(chat_request.model, "请求处理过程中发生错误，请重试")
    except Exception as e:
        # 处理API任务异常
        error_msg = str(e)
        extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message': error_msg}
        log('error', f"客户端断开后处理API响应时出错: {error_msg}", extra=extra_log)
        
        # 删除缓存，因为出现错误
        if cache_key and cache_key in response_cache_manager.cache:
            log('info', f"因API响应错误，删除缓存: {cache_key[:8]}...", 
                extra={'cache_operation': 'remove-on-error', 'request_type': request_type})
            del response_cache_manager.cache[cache_key]
            
        # 创建错误响应而不是返回None
        return create_error_response(chat_request.model, f"请求处理错误: {error_msg}")

async def process_nonstream_request(
    chat_request: ChatCompletionRequest, 
    http_request: Request, 
    request_type: str,
    contents,
    system_instruction,
    current_api_key: str,
    cache_key: str = None,
    client_ip: str = None
):
    """处理非流式API请求"""
    gemini_client = GeminiClient(current_api_key)
    
    # 创建任务
    gemini_task = asyncio.create_task(
        run_gemini_completion(
            gemini_client,
            chat_request,
            contents,
            system_instruction,
            request_type,
            current_api_key
        )
    )
    
    disconnect_task = asyncio.create_task(
        check_client_disconnect(
            http_request,
            current_api_key,
            request_type,
            chat_request.model
        )
    )

    try:
        # 先等待看是否API任务先完成，或者客户端先断开连接
        done, pending = await asyncio.wait(
            [gemini_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        if disconnect_task in done:
            # 客户端已断开连接，但我们仍继续完成API请求以便缓存结果
            return await handle_client_disconnect(
                gemini_task,
                chat_request,
                request_type,
                current_api_key,
                cache_key,
                client_ip
            )
        else:
            # API任务先完成，取消断开检测任务
            disconnect_task.cancel()
            
            # 获取响应内容
            response_content = await gemini_task
            
            # 检查缓存是否已经存在，如果存在则不再创建新缓存
            cached_response, cache_hit = response_cache_manager.get(cache_key)
            if cache_hit:
                log('info', f"缓存已存在，直接返回: {cache_key[:8]}...", 
                    extra={'cache_operation': 'use-existing', 'request_type': request_type})
                
                # 安全删除缓存
                if cache_key in response_cache_manager.cache:
                    del response_cache_manager.cache[cache_key]
                    log('info', f"缓存使用后已删除: {cache_key[:8]}...", 
                        extra={'cache_operation': 'used-and-removed', 'request_type': request_type})
                
                return cached_response
            
            # 创建响应
            response = create_response(chat_request, response_content)
            
            # 缓存响应
            cache_response(response, cache_key, client_ip)
            
            # 立即删除缓存，确保只能使用一次
            if cache_key and cache_key in response_cache_manager.cache:
                del response_cache_manager.cache[cache_key]
                log('info', f"缓存创建后立即删除: {cache_key[:8]}...", 
                    extra={'cache_operation': 'store-and-remove', 'request_type': request_type})
            
            # 返回响应
            return response

    except asyncio.CancelledError:
        extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message':"请求被取消"}
        log('info', "请求取消", extra=extra_log)
        
        # 在请求被取消时先检查缓存中是否已有结果
        cached_response, cache_hit = response_cache_manager.get(cache_key)
        if cache_hit:
            log('info', f"请求取消但找到有效缓存，使用缓存响应: {cache_key[:8]}...", 
                extra={'cache_operation': 'use-cache-on-cancel', 'request_type': request_type})
            
            # 安全删除缓存
            if cache_key in response_cache_manager.cache:
                del response_cache_manager.cache[cache_key]
                log('info', f"缓存使用后已删除: {cache_key[:8]}...", 
                    extra={'cache_operation': 'used-and-removed', 'request_type': request_type})
            
            return cached_response
            
        # 尝试完成正在进行的API请求
        if not gemini_task.done():
            log('info', "请求取消但API请求尚未完成，继续等待...", 
                extra={'key': current_api_key[:8], 'request_type': request_type})
            
            # 使用shield确保任务不会被取消
            response_content = await asyncio.shield(gemini_task)
            
            # 创建响应
            response = create_response(chat_request, response_content)
            
            # 不缓存这个响应，直接返回
            return response
        else:
            # 任务已完成，获取结果
            response_content = gemini_task.result()
            
            # 创建响应
            response = create_response(chat_request, response_content)
            
            # 不缓存这个响应，直接返回
            return response

    except HTTPException as e:
        if e.status_code == status.HTTP_408_REQUEST_TIMEOUT:
            extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 
                        'status_code': 408, 'error_message': '客户端连接中断'}
            log('error', "客户端连接中断，终止后续重试", extra=extra_log)
            raise  
        else:
            raise

# 添加通用响应处理函数
def create_response(
    chat_request, response_content
):
    """创建标准响应对象但不缓存"""
    # 创建响应对象
    return create_chat_response(
        model=chat_request.model,
        choices=[{
            "index": 0, 
            "message": {
                "role": "assistant", 
                "content": response_content.text
            }, 
            "finish_reason": "stop"
        }]
    )

def cache_response(response, cache_key, client_ip):
    """将响应存入缓存"""
    if not cache_key:
        return
        
    # 先检查缓存是否已存在
    existing_cache = cache_key in response_cache_manager.cache
    
    if existing_cache:
        log('info', f"缓存已存在，跳过存储: {cache_key[:8]}...", 
            extra={'cache_operation': 'skip-existing', 'request_type': 'non-stream'})
    else:
        response_cache_manager.store(cache_key, response, client_ip)
        log('info', f"API响应已缓存: {cache_key[:8]}...", 
            extra={'cache_operation': 'store-new', 'request_type': 'non-stream'})
    
    # 更新API调用统计
    update_api_call_stats()

# 统一的API错误处理函数
async def handle_api_error(e, api_key, key_manager, request_type, model, retry_count=0):
    """统一处理API错误，对500和503错误实现自动重试机制"""
    error_detail = handle_gemini_error(e, api_key, key_manager)
    
    # 处理500和503服务器错误
    if isinstance(e, requests.exceptions.HTTPError) and ('500' in str(e) or '503' in str(e)):
        status_code = '500' if '500' in str(e) else '503'
        
        # 最多重试3次
        if retry_count < 3:
            wait_time = min(RETRY_DELAY * (2 ** retry_count), MAX_RETRY_DELAY)
            log('warning', f"Gemini服务器错误({status_code})，等待{wait_time}秒后重试 ({retry_count+1}/3)", 
                key=api_key[:8], request_type=request_type, model=model, status_code=int(status_code))
            
            # 等待后返回重试信号
            await asyncio.sleep(wait_time)
            return {'should_retry': True, 'error': error_detail, 'remove_cache': False}
        
        # 重试次数用尽，直接返回错误状态码
        log('error', f"服务器错误({status_code})重试{retry_count}次后仍然失败", 
            key=api_key[:8], request_type=request_type, model=model, status_code=int(status_code))
        
        # 不建议切换密钥，直接抛出HTTP异常
        raise HTTPException(status_code=int(status_code), 
                          detail=f"Gemini API 服务器错误({status_code})，请稍后重试")
    
    # 对于其他错误，返回切换密钥的信号
    log('error', f"API错误: {error_detail}", 
        key=api_key[:8], request_type=request_type, model=model, error_message=error_detail)
    return {'should_retry': False, 'should_switch_key': True, 'error': error_detail, 'remove_cache': True}