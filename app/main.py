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


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.excepthook(exc_type, exc_value, exc_traceback)
        return
    error_message = translate_error(str(exc_value))
    log_msg = format_log_message('ERROR', f"未捕获的异常: %s" % error_message, extra={'status_code': 500, 'error_message': error_message})
    logger.error(log_msg)


sys.excepthook = handle_exception
app = FastAPI()

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
    
    log_msg = format_log_message('INFO', f"API调用统计已更新: 24小时={sum(api_call_stats['last_24h'].values())}, 1小时={sum(api_call_stats['hourly'].values())}, 1分钟={sum(api_call_stats['minute'].values())}")
    logger.info(log_msg)

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


def switch_api_key():
    global current_api_key
    key = key_manager.get_available_key() # get_available_key 会处理栈的逻辑
    if key:
        current_api_key = key
        log_msg = format_log_message('INFO', f"API key 替换为 → {current_api_key[:8]}...", extra={'key': current_api_key[:8], 'request_type': 'switch_key'})
        logger.info(log_msg)
    else:
        log_msg = format_log_message('ERROR', "API key 替换失败，所有API key都已尝试，请重新配置或稍后重试", extra={'key': 'N/A', 'request_type': 'switch_key', 'status_code': 'N/A'})
        logger.error(log_msg)


async def check_keys():
    available_keys = []
    for key in key_manager.api_keys:
        is_valid = await test_api_key(key)
        status_msg = "有效" if is_valid else "无效"
        log_msg = format_log_message('INFO', f"API Key {key[:10]}... {status_msg}.")
        logger.info(log_msg)
        if is_valid:
            available_keys.append(key)
    if not available_keys:
        log_msg = format_log_message('ERROR', "没有可用的 API 密钥！", extra={'key': 'N/A', 'request_type': 'startup', 'status_code': 'N/A'})
        logger.error(log_msg)
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
            
            log_msg = format_log_message('INFO', f"版本检查: 本地版本 {local_version}, 远程版本 {remote_version}, 有更新: {has_update}")
            logger.info(log_msg)
        else:
            log_msg = format_log_message('WARNING', f"无法获取远程版本信息，HTTP状态码: {response.status_code}")
            logger.warning(log_msg)
    except Exception as e:
        log_msg = format_log_message('ERROR', f"版本检查失败: {str(e)}")
        logger.error(log_msg)

@app.on_event("startup")
async def startup_event():
    log_msg = format_log_message('INFO', "Starting Gemini API proxy...")
    logger.info(log_msg)
    
    # 启动缓存清理定时任务
    schedule_cache_cleanup()
    
    # 检查版本
    await check_version()
    
    available_keys = await check_keys()
    if available_keys:
        key_manager.api_keys = available_keys
        key_manager._reset_key_stack() # 启动时也确保创建随机栈
        key_manager.show_all_keys()
        log_msg = format_log_message('INFO', f"可用 API 密钥数量：{len(key_manager.api_keys)}")
        logger.info(log_msg)
        # MAX_RETRIES = len(key_manager.api_keys)
        log_msg = format_log_message('INFO', f"最大重试次数设置为：{len(key_manager.api_keys)}") # 添加日志
        logger.info(log_msg)
        if key_manager.api_keys:
            all_models = await GeminiClient.list_available_models(key_manager.api_keys[0])
            GeminiClient.AVAILABLE_MODELS = [model.replace(
                "models/", "") for model in all_models]
            log_msg = format_log_message('INFO', "Available models loaded.")
            logger.info(log_msg)

@app.get("/v1/models", response_model=ModelList)
def list_models():
    log_msg = format_log_message('INFO', "Received request to list models", extra={'request_type': 'list_models', 'status_code': 200})
    logger.info(log_msg)
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
    
    # 生成简化请求特征键（主要基于模型和消息内容）- 用于相似匹配
    simplified_key = generate_simplified_request_key(client_ip, request.model, request.messages)
    
    # 记录请求缓存键信息
    log_msg = format_log_message('INFO', f"请求缓存键: {cache_key[:8]}..., 简化键: {simplified_key[:8]}...", 
                               extra={'cache_key': cache_key[:8], 'request_type': 'non-stream'})
    logger.info(log_msg)
    
    # 检查精确缓存是否存在且未过期
    if cache_key in response_cache and time.time() < response_cache[cache_key].get('expiry_time', 0):
        # 精确缓存命中
        log_msg = format_log_message('INFO', f"精确缓存命中: {cache_key[:8]}...", 
                                   extra={'cache_operation': 'hit', 'request_type': 'non-stream'})
        logger.info(log_msg)
        
        # 获取缓存的响应
        cached_response = response_cache[cache_key]['response']
        
        # 根据配置决定是否删除缓存项
        if REMOVE_CACHE_AFTER_USE:
            del response_cache[cache_key]
            log_msg = format_log_message('INFO', f"缓存使用后已清除: {cache_key[:8]}...", 
                                      extra={'cache_operation': 'used-and-removed', 'request_type': 'non-stream'})
            logger.info(log_msg)
            
            # 同时清理相关的活跃任务，避免后续请求等待已经不需要的任务
            task_keys_to_delete = []
            for task_key in active_requests_pool.keys():
                if task_key.startswith(f"cache:{cache_key}:"):
                    task_keys_to_delete.append(task_key)
            
            for task_key in task_keys_to_delete:
                if task_key in active_requests_pool:
                    # 不取消任务，只从池中移除，避免任务被中断
                    del active_requests_pool[task_key]
                    log_msg = format_log_message('INFO', f"缓存使用后移除相关活跃任务: {task_key}", 
                                              extra={'cache_operation': 'task-removed', 'request_type': 'non-stream'})
                    logger.info(log_msg)
        
        # 返回缓存响应（但创建新的响应对象）
        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time()*1000)}",
            object="chat.completion", 
            created=int(time.time()),
            model=cached_response.model,
            choices=cached_response.choices
        )
    
    # 查找所有使用相同缓存键的活跃任务
    for key, task in active_requests_pool.items():
        if not task.done() and key.startswith(f"cache:{cache_key}"):
            log_msg = format_log_message('INFO', f"发现相同请求的进行中任务", 
                                      extra={'request_type': 'non-stream', 'model': request.model})
            logger.info(log_msg)
            
            # 等待已有任务完成
            try:
                # 设置超时，避免无限等待
                result = await asyncio.wait_for(task, timeout=60)
                # 如果任务成功完成，返回结果
                if result:
                    log_msg = format_log_message('INFO', f"使用已完成任务的结果", 
                                              extra={'request_type': 'non-stream', 'model': request.model})
                    logger.info(log_msg)
                    
                    # 如果配置了使用后清除缓存，检查并清除相关缓存
                    if REMOVE_CACHE_AFTER_USE:
                        # 从活跃任务键中提取缓存键
                        parts = key.split(":")
                        if len(parts) >= 2 and parts[0] == "cache":
                            cache_key_from_task = parts[1]
                            if cache_key_from_task in response_cache:
                                del response_cache[cache_key_from_task]
                                log_msg = format_log_message('INFO', f"活跃任务完成后清除缓存: {cache_key_from_task[:8]}...", 
                                                          extra={'cache_operation': 'task-used-and-removed', 'request_type': 'non-stream'})
                                logger.info(log_msg)
                    
                    # 返回活跃任务的结果
                    return ChatCompletionResponse(
                        id=f"chatcmpl-{int(time.time()*1000)}",
                        object="chat.completion", 
                        created=int(time.time()),
                        model=result.model,
                        choices=result.choices
                    )
            except (asyncio.TimeoutError, asyncio.CancelledError) as e:
                # 任务超时或被取消的情况下，记录日志然后让代码继续执行
                # 不要重新抛出异常
                error_type = "超时" if isinstance(e, asyncio.TimeoutError) else "被取消"
                log_msg = format_log_message('WARNING', f"等待已有任务{error_type}: {key}", 
                                          extra={'request_type': 'non-stream', 'model': request.model})
                logger.warning(log_msg)
                
                # 从活跃请求池移除该任务
                if key in active_requests_pool and (task.done() or task.cancelled()):
                    del active_requests_pool[key]
                    log_msg = format_log_message('INFO', f"已从活跃请求池移除{error_type}任务: {key}", 
                                              extra={'request_type': 'non-stream'})
                    logger.info(log_msg)
                    
                # 不抛出异常，继续处理，尝试查找其他缓存或创建新请求
    
    # 检查相似缓存 - 查找来自任何客户端的相似请求缓存
    for key, cache_data in response_cache.items():
        # 检查是否有相同模型、相似内容的已缓存响应
        simplified_stored = cache_data.get('simplified_key')
        if (simplified_stored == simplified_key and 
            time.time() < cache_data.get('expiry_time', 0)):
            
            log_msg = format_log_message('INFO', f"相似缓存命中: {key[:8]}... (简化键: {simplified_key[:8]}...)", 
                                       extra={'cache_operation': 'similar-hit', 'request_type': 'non-stream'})
            logger.info(log_msg)
            
            # 获取缓存的响应
            cached_response = cache_data['response']
            
            # 根据配置决定是否删除缓存项
            if REMOVE_CACHE_AFTER_USE:
                del response_cache[key]
                log_msg = format_log_message('INFO', f"相似缓存使用后已清除: {key[:8]}...", 
                                          extra={'cache_operation': 'similar-used-and-removed', 'request_type': 'non-stream'})
                logger.info(log_msg)
                
                # 同时清理相关的活跃任务，避免后续请求等待已经不需要的任务
                task_keys_to_delete = []
                for task_key in active_requests_pool.keys():
                    if task_key.startswith(f"cache:{key}:") or task_key.endswith(f":{simplified_key}"):
                        task_keys_to_delete.append(task_key)
                
                for task_key in task_keys_to_delete:
                    if task_key in active_requests_pool:
                        # 不取消任务，只从池中移除，避免任务被中断
                        del active_requests_pool[task_key]
                        log_msg = format_log_message('INFO', f"相似缓存使用后移除相关活跃任务: {task_key}", 
                                                  extra={'cache_operation': 'similar-task-removed', 'request_type': 'non-stream'})
                        logger.info(log_msg)
            
            # 返回缓存响应（但创建新的响应对象）
            return ChatCompletionResponse(
                id=f"chatcmpl-{int(time.time()*1000)}",
                object="chat.completion", 
                created=int(time.time()),
                model=cached_response.model,
                choices=cached_response.choices
            )
    
    # 构建包含缓存键的活跃请求池键
    pool_key = f"cache:{cache_key}:{simplified_key}"
    
    # 创建请求处理任务
    process_task = asyncio.create_task(
        process_request(request, http_request, "non-stream", cache_key=cache_key, client_ip=client_ip, simplified_key=simplified_key)
    )
    
    # 给任务添加创建时间属性，用于清理长时间运行的任务
    process_task.creation_time = time.time()
    
    # 将任务添加到活跃请求池
    active_requests_pool[pool_key] = process_task
    
    # 等待任务完成
    try:
        response = await process_task
        # 检查结果是否为None（表示任务被取消）
        if response is None:
            log_msg = format_log_message('INFO', f"任务已被取消，回退到创建新请求", 
                                      extra={'request_type': 'non-stream', 'model': request.model})
            logger.info(log_msg)
            
            # 如果在活跃请求池中，移除任务
            if pool_key in active_requests_pool:
                del active_requests_pool[pool_key]
            
            # 创建新的处理任务（不添加到活跃请求池，避免重复问题）
            new_process_task = asyncio.create_task(
                process_request(request, http_request, "non-stream", cache_key=cache_key, client_ip=client_ip, simplified_key=simplified_key)
            )
            
            # 等待新任务完成
            response = await new_process_task
            if response is None:
                # 如果新任务也被取消，则返回错误
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                    detail="请求处理失败，任务被取消"
                )
        
        return response
    except Exception as e:
        # 如果任务失败，从活跃请求池中移除
        if pool_key in active_requests_pool:
            del active_requests_pool[pool_key]
        raise

async def process_request(chat_request: ChatCompletionRequest, http_request: Request, request_type: Literal['stream', 'non-stream'], cache_key: str = None, client_ip: str = None, simplified_key: str = None):
    global current_api_key
    protect_from_abuse(
        http_request, MAX_REQUESTS_PER_MINUTE, MAX_REQUESTS_PER_DAY_PER_IP)
    if chat_request.model not in GeminiClient.AVAILABLE_MODELS:
        error_msg = "无效的模型"
        extra_log = {'request_type': request_type, 'model': chat_request.model, 'status_code': 400, 'error_message': error_msg}
        log_msg = format_log_message('ERROR', error_msg, extra=extra_log)
        logger.error(log_msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    key_manager.reset_tried_keys_for_request() # 在每次请求处理开始时重置 tried_keys 集合

    contents, system_instruction = GeminiClient.convert_messages(
        GeminiClient, chat_request.messages)

    retry_attempts = len(key_manager.api_keys) if key_manager.api_keys else 1 # 重试次数等于密钥数量，至少尝试 1 次
    for attempt in range(1, retry_attempts + 1):
        if attempt == 1:
            current_api_key = key_manager.get_available_key() # 每次循环开始都获取新的 key, 栈逻辑在 get_available_key 中处理
        
        if current_api_key is None: # 检查是否获取到 API 密钥
            log_msg_no_key = format_log_message('WARNING', "没有可用的 API 密钥，跳过本次尝试", extra={'request_type': request_type, 'model': chat_request.model, 'status_code': 'N/A'})
            logger.warning(log_msg_no_key)
            break  # 如果没有可用密钥，跳出循环

        extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'status_code': 'N/A', 'error_message': ''}
        log_msg = format_log_message('INFO', f"第 {attempt}/{retry_attempts} 次尝试 ... 使用密钥: {current_api_key[:8]}...", extra=extra_log)
        logger.info(log_msg)

        gemini_client = GeminiClient(current_api_key)
        try:
            if chat_request.stream:
                async def stream_generator():
                    try:
                        # 标记是否成功获取到响应
                        success = False
                        async for chunk in gemini_client.stream_chat(chat_request, contents, safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings, system_instruction):
                            formatted_chunk = {"id": "chatcmpl-someid", "object": "chat.completion.chunk", "created": 1234567,
                                               "model": chat_request.model, "choices": [{"delta": {"role": "assistant", "content": chunk}, "index": 0, "finish_reason": None}]}
                            success = True  # 只要有一个chunk成功，就标记为成功
                            yield f"data: {json.dumps(formatted_chunk)}\n\n"
                        
                        # 如果成功获取到响应，更新API调用统计
                        if success:
                            update_api_call_stats()
                            
                        yield "data: [DONE]\n\n"

                    except asyncio.CancelledError:
                        extra_log_cancel = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message': '客户端已断开连接'}
                        log_msg = format_log_message('INFO', "客户端连接已中断", extra=extra_log_cancel)
                        logger.info(log_msg)
                    except Exception as e:
                        error_detail = handle_gemini_error(
                            e, current_api_key, key_manager)
                        yield f"data: {json.dumps({'error': {'message': error_detail, 'type': 'gemini_error'}})}\n\n"
                return StreamingResponse(stream_generator(), media_type="text/event-stream")
            else:
                async def run_gemini_completion():
                    try:
                        response_content = await asyncio.to_thread(gemini_client.complete_chat, chat_request, contents, safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings, system_instruction)
                        return response_content
                    except asyncio.CancelledError:
                        extra_log_gemini_cancel = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message': '客户端断开导致API调用取消'}
                        log_msg = format_log_message('INFO', "API调用因客户端断开而取消", extra=extra_log_gemini_cancel)
                        logger.info(log_msg)
                        # 不继续抛出异常，而是返回None，表示任务被取消
                        return None

                async def check_client_disconnect():
                    while True:
                        if await http_request.is_disconnected():
                            extra_log_client_disconnect = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message': '检测到客户端断开连接'}
                            log_msg = format_log_message('INFO', "客户端连接已中断，等待API请求完成", extra=extra_log_client_disconnect)
                            logger.info(log_msg)
                            return True
                        await asyncio.sleep(0.5)

                gemini_task = asyncio.create_task(run_gemini_completion())
                disconnect_task = asyncio.create_task(check_client_disconnect())

                try:
                    done, pending = await asyncio.wait(
                        [gemini_task, disconnect_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    if disconnect_task in done:
                        # 不立即取消API请求，而是等待其完成
                        try:
                            response_content = await gemini_task
                            # 检查响应内容是否为None（表示任务被取消）
                            if response_content is None:
                                log_msg = format_log_message('INFO', "API任务已取消，跳过处理", 
                                    extra={'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model})
                                logger.info(log_msg)
                                # 继续循环，尝试其他API密钥
                                continue
                            
                            # 检查响应文本是否为空
                            if response_content.text == "":
                                extra_log_empty_response = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'status_code': 204}
                                log_msg = format_log_message('INFO', "Gemini API 返回空响应", extra=extra_log_empty_response)
                                logger.info(log_msg)
                                # 继续循环
                                continue
                            
                            # 生成符合OpenAI标准的响应ID
                            response_id = f"chatcmpl-{int(time.time()*1000)}"
                            
                            response = ChatCompletionResponse(
                                id=response_id,
                                object="chat.completion", 
                                created=int(time.time()),
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
                            
                            # 缓存响应
                            if cache_key:
                                now = time.time()
                                response_cache[cache_key] = {
                                    'response': response,
                                    'expiry_time': now + CACHE_EXPIRY_TIME,
                                    'created_at': now,
                                    'client_ip': client_ip,
                                    'simplified_key': simplified_key
                                }
                                log_msg = format_log_message('INFO', f"响应已缓存: {cache_key[:8]}...", 
                                                           extra={'cache_operation': 'store', 'request_type': request_type})
                                logger.info(log_msg)
                            
                            extra_log_success = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'status_code': 200}
                            log_msg = format_log_message('INFO', "请求处理成功", extra=extra_log_success)
                            logger.info(log_msg)
                            
                            # 更新API调用统计
                            update_api_call_stats()
                            
                            return response
                        except Exception as e:
                            extra_log_error = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'status_code': 408, 'error_message': 'API请求失败'}
                            log_msg = format_log_message('ERROR', "API请求失败", extra=extra_log_error)
                            logger.error(log_msg)
                            raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail="API请求失败")

                    if gemini_task in done:
                        disconnect_task.cancel()
                        try:
                            await disconnect_task
                        except asyncio.CancelledError:
                            pass
                        response_content = gemini_task.result()
                        if response_content.text == "":
                            extra_log_empty_response = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'status_code': 204}
                            log_msg = format_log_message('INFO', "Gemini API 返回空响应", extra=extra_log_empty_response)
                            logger.info(log_msg)
                            # 继续循环
                            continue
                        
                        # 生成符合OpenAI标准的响应ID
                        response_id = f"chatcmpl-{int(time.time()*1000)}"
                        
                        response = ChatCompletionResponse(
                            id=response_id,
                            object="chat.completion", 
                            created=int(time.time()),
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
                        
                        # 缓存响应
                        if cache_key:
                            now = time.time()
                            response_cache[cache_key] = {
                                'response': response,
                                'expiry_time': now + CACHE_EXPIRY_TIME,
                                'created_at': now,
                                'client_ip': client_ip,
                                'simplified_key': simplified_key
                            }
                            log_msg = format_log_message('INFO', f"响应已缓存: {cache_key[:8]}...", 
                                        extra={'cache_operation': 'store', 'request_type': request_type})
                            logger.info(log_msg)
                        
                        extra_log_success = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'status_code': 200}
                        log_msg = format_log_message('INFO', "请求处理成功", extra=extra_log_success)
                        logger.info(log_msg)
                        
                        # 更新API调用统计
                        update_api_call_stats()
                        
                        return response

                except asyncio.CancelledError:
                    extra_log_request_cancel = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 'error_message':"请求被取消" }
                    log_msg = format_log_message('INFO', "请求取消", extra=extra_log_request_cancel)
                    logger.info(log_msg)
                    
                    # 在请求被取消时清理相关资源
                    for pool_key in list(active_requests_pool.keys()):
                        if cache_key and pool_key.startswith(f"cache:{cache_key}:"):
                            del active_requests_pool[pool_key]
                            log_msg = format_log_message('INFO', f"请求取消时清理相关活跃任务: {pool_key}", 
                                                      extra={'cleanup': 'cancelled_task'})
                            logger.info(log_msg)
                    
                    # 不再抛出CancelledError，而是返回None，使用另一种方法处理取消
                    return None

        except HTTPException as e:
            if e.status_code == status.HTTP_408_REQUEST_TIMEOUT:
                extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': chat_request.model, 
                            'status_code': 408, 'error_message': '客户端连接中断'}
                log_msg = format_log_message('ERROR', "客户端连接中断，终止后续重试", extra=extra_log)
                logger.error(log_msg)
                raise  
            else:
                raise  
        except Exception as e:
            handle_gemini_error(e, current_api_key, key_manager)
            if attempt < retry_attempts: 
                switch_api_key() 
                continue

    msg = "所有API密钥均失败,请稍后重试"
    extra_log_all_fail = {'key': "ALL", 'request_type': request_type, 'model': chat_request.model, 'status_code': 500, 'error_message': msg}
    log_msg = format_log_message('ERROR', msg, extra=extra_log_all_fail)
    logger.error(log_msg)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_message = translate_error(str(exc))
    extra_log_unhandled_exception = {'status_code': 500, 'error_message': error_message}
    log_msg = format_log_message('ERROR', f"Unhandled exception: {error_message}", extra=extra_log_unhandled_exception)
    logger.error(log_msg)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=ErrorResponse(message=str(exc), type="internal_error").dict())


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # 先清理过期数据，确保统计数据是最新的
    clean_expired_stats()
    clean_expired_cache()
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
    total_cache = len(response_cache)
    valid_cache = 0
    cache_by_model = {}
    recent_cache_operations = []
    
    # 分析缓存数据
    for cache_key, cache_data in response_cache.items():
        if time.time() < cache_data.get('expiry_time', 0):
            valid_cache += 1
            
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
    active_count = len(active_requests_pool)
    active_done = sum(1 for task in active_requests_pool.values() if task.done())
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
        "active_pending": active_pending
    }
    
    # 使用Jinja2模板引擎正确渲染HTML
    return templates.TemplateResponse("index.html", {"request": request, **context})

# 请求响应缓存
response_cache: Dict[str, Dict[str, Any]] = {}
# 活跃请求池 - 存储正在处理的请求
active_requests_pool: Dict[str, asyncio.Task] = {}
# 缓存过期时间（秒）
CACHE_EXPIRY_TIME = int(os.environ.get("CACHE_EXPIRY_TIME", "300"))  # 默认5分钟
# 是否在缓存命中后立即清除
REMOVE_CACHE_AFTER_USE = os.environ.get("REMOVE_CACHE_AFTER_USE", "true").lower() in ["true", "1", "yes"]
# 客户端IP到最近请求的映射，用于识别重连请求
client_request_history: Dict[str, Dict[str, Any]] = {}
# 请求历史记录保留时间（秒）
REQUEST_HISTORY_EXPIRY_TIME = int(os.environ.get("REQUEST_HISTORY_EXPIRY_TIME", "600"))  # 默认10分钟
# 是否启用重连检测
ENABLE_RECONNECT_DETECTION = os.environ.get("ENABLE_RECONNECT_DETECTION", "true").lower() in ["true", "1", "yes"]
# 缓存大小限制（项数）
MAX_CACHE_ENTRIES = int(os.environ.get("MAX_CACHE_ENTRIES", "1000"))  # 默认最多缓存1000条响应

# 清理过期的活跃请求
def clean_expired_active_requests():
    now = time.time()
    expired_keys = []
    
    for req_key, task in active_requests_pool.items():
        if task.done() or task.cancelled():
            expired_keys.append(req_key)
    
    for key in expired_keys:
        del active_requests_pool[key]
    
    if expired_keys:
        log_msg = format_log_message('INFO', f"清理已完成请求任务: {len(expired_keys)}个", extra={'cleanup': 'active_requests'})
        logger.info(log_msg)
    
    # 检查长时间运行的任务（超过5分钟）
    long_running_keys = []
    # 任务开始时间是在构建池键之前记录的，这里使用粗略估计
    five_minutes_ago = now - 300  # 5分钟 = 300秒
    
    for req_key, task in active_requests_pool.items():
        if req_key.startswith("cache:") and not task.done() and not task.cancelled():
            # 检查任务是否已经运行太长时间
            if hasattr(task, 'creation_time') and task.creation_time < five_minutes_ago:
                long_running_keys.append(req_key)
                # 取消长时间运行的任务
                task.cancel()
    
    if long_running_keys:
        log_msg = format_log_message('WARNING', f"取消长时间运行的任务: {len(long_running_keys)}个", extra={'cleanup': 'long_running_tasks'})
        logger.warning(log_msg)

# 生成简化的请求特征键
def generate_simplified_request_key(client_ip: str, model: str, messages: list) -> str:
    """
    生成一个简化的请求特征键，用于快速识别相似请求
    主要基于模型和消息内容，不依赖客户端IP（因为酒馆重试时可能使用不同连接）
    """
    # 收集所有用户消息形成特征
    user_messages = []
    for msg in messages:
        if msg.role == "user":
            if isinstance(msg.content, str):
                user_messages.append(msg.content[:100])  # 只取前100个字符
    
    # 使用最后一条用户消息和消息数量作为特征
    last_message = user_messages[-1] if user_messages else ""
    message_count = len(messages)
    
    # 计算消息总长度作为特征
    total_length = sum(len(m.content) if isinstance(m.content, str) else 10 for m in messages)
    
    # 组合特征生成键 - 不包含客户端IP，因为重试请求的IP特征可能会变化
    feature_string = f"{model}:{message_count}:{total_length}:{last_message[:100]}"
    return hashlib.md5(feature_string.encode()).hexdigest()

# 清理过期缓存的函数
def clean_expired_cache():
    now = time.time()
    expired_keys = []
    
    # 找出过期的缓存项
    for cache_key, cache_data in response_cache.items():
        if now > cache_data.get('expiry_time', 0):
            expired_keys.append(cache_key)
    
    # 删除过期的缓存项
    for key in expired_keys:
        log_msg = format_log_message('INFO', f"清理过期缓存: {key[:8]}...", extra={'cache_operation': 'clean'})
        logger.info(log_msg)
        del response_cache[key]
    
    # 如果缓存数量超过限制，清除最旧的缓存
    if len(response_cache) > MAX_CACHE_ENTRIES:
        # 按创建时间排序
        sorted_keys = sorted(response_cache.keys(), 
                           key=lambda k: response_cache[k].get('created_at', 0))
        
        # 计算需要删除的数量
        to_remove = len(response_cache) - MAX_CACHE_ENTRIES
        
        # 删除最旧的项
        for key in sorted_keys[:to_remove]:
            log_msg = format_log_message('INFO', f"缓存容量限制，删除旧缓存: {key[:8]}...", 
                                       extra={'cache_operation': 'limit'})
            logger.info(log_msg)
            del response_cache[key]
    
    # 同时清理过期的请求历史记录
    expired_ips = []
    for client_ip, history_data in client_request_history.items():
        if now > history_data.get('expiry_time', 0):
            expired_ips.append(client_ip)
    
    for ip in expired_ips:
        del client_request_history[ip]

# 定期清理缓存的定时任务
def schedule_cache_cleanup():
    scheduler = BackgroundScheduler()
    scheduler.add_job(clean_expired_cache, 'interval', minutes=1)  # 每分钟清理一次
    scheduler.add_job(clean_expired_active_requests, 'interval', seconds=30)  # 每30秒清理一次活跃请求
    scheduler.start()

# 添加请求历史记录，用于识别重连请求
def record_client_request(client_ip: str, request_data: Dict[str, Any]):
    now = time.time()
    client_request_history[client_ip] = {
        'request_data': request_data,
        'timestamp': now,
        'expiry_time': now + REQUEST_HISTORY_EXPIRY_TIME
    }

# 提取请求的关键特征，用于识别相似请求
def extract_request_features(request: ChatCompletionRequest) -> Dict[str, Any]:
    # 创建包含请求关键信息的字典
    features = {
        'model': request.model,
        'temperature': request.temperature,
        'max_tokens': request.max_tokens,
        'last_message': ''
    }
    
    # 提取最后一条用户消息
    for msg in reversed(request.messages):
        if msg.role == "user":
            if isinstance(msg.content, str):
                features['last_message'] = msg.content[:100]  # 只取前100个字符
            break
    
    return features

# 检查当前请求是否与客户端之前的请求相似（可能是重连请求）
def is_reconnect_request(client_ip: str, current_request: Dict[str, Any]) -> bool:
    if client_ip not in client_request_history:
        return False
    
    previous_request = client_request_history[client_ip]['request_data']
    
    # 比较模型、温度和最大令牌数
    if (previous_request['model'] != current_request['model'] or
        abs(previous_request['temperature'] - current_request['temperature']) > 0.001 or
        previous_request['max_tokens'] != current_request['max_tokens']):
        return False
    
    # 检查最后一条消息是否相似（前50个字符）
    prev_msg = previous_request['last_message'][:50]
    curr_msg = current_request['last_message'][:50]
    
    # 如果最后一条消息完全相同，很可能是重连请求
    if prev_msg == curr_msg and prev_msg != "":
        return True
    
    return False

# 生成请求的唯一缓存键
def generate_cache_key(chat_request: ChatCompletionRequest) -> str:
    # 创建包含请求关键信息的字典
    request_data = {
        'model': chat_request.model,
        'temperature': chat_request.temperature,
        'max_tokens': chat_request.max_tokens,
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