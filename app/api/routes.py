from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse, StreamingResponse
from app.models import ChatCompletionRequest, ChatCompletionResponse, ErrorResponse, ModelList
from app.services import GeminiClient, ResponseWrapper
from app.utils import (
    handle_gemini_error, 
    protect_from_abuse, 
    APIKeyManager, 
    test_api_key, 
    format_log_message, 
    log_manager,
    generate_cache_key,
    cache_response,
    create_chat_response,
    create_error_response,
    handle_api_error
)
import json
import asyncio
import time
import logging
from typing import Literal

# 获取logger
logger = logging.getLogger("my_logger")

# 创建路由器
router = APIRouter()

# 全局变量引用 - 这些将在main.py中初始化并传递给路由
key_manager = None
response_cache_manager = None
active_requests_manager = None
safety_settings = None
safety_settings_g2 = None
current_api_key = None
FAKE_STREAMING = None
FAKE_STREAMING_INTERVAL = None
PASSWORD = None
MAX_REQUESTS_PER_MINUTE = None
MAX_REQUESTS_PER_DAY_PER_IP = None

# 初始化路由器的函数
def init_router(
    _key_manager,
    _response_cache_manager,
    _active_requests_manager,
    _safety_settings,
    _safety_settings_g2,
    _current_api_key,
    _fake_streaming,
    _fake_streaming_interval,
    _password,
    _max_requests_per_minute,
    _max_requests_per_day_per_ip
):
    global key_manager, response_cache_manager, active_requests_manager
    global safety_settings, safety_settings_g2, current_api_key
    global FAKE_STREAMING, FAKE_STREAMING_INTERVAL
    global PASSWORD, MAX_REQUESTS_PER_MINUTE, MAX_REQUESTS_PER_DAY_PER_IP
    
    key_manager = _key_manager
    response_cache_manager = _response_cache_manager
    active_requests_manager = _active_requests_manager
    safety_settings = _safety_settings
    safety_settings_g2 = _safety_settings_g2
    current_api_key = _current_api_key
    FAKE_STREAMING = _fake_streaming
    FAKE_STREAMING_INTERVAL = _fake_streaming_interval
    PASSWORD = _password
    MAX_REQUESTS_PER_MINUTE = _max_requests_per_minute
    MAX_REQUESTS_PER_DAY_PER_IP = _max_requests_per_day_per_ip

# 日志记录函数
def log(level: str, message: str, **extra):
    """简化日志记录的统一函数"""
    msg = format_log_message(level.upper(), message, extra=extra)
    getattr(logger, level.lower())(msg)

# 密码验证依赖
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

# API路由
@router.get("/v1/models", response_model=ModelList)
def list_models():
    log('info', "Received request to list models", extra={'request_type': 'list_models', 'status_code': 200})
    return ModelList(data=[{"id": model, "object": "model", "created": 1678888888, "owned_by": "organization-owner"} for model in GeminiClient.AVAILABLE_MODELS])

@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
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

# 请求处理函数
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
                    try:
                        return await process_stream_request(
                            chat_request,
                            http_request,
                            contents,
                            system_instruction,
                            current_api_key
                        )
                    except Exception as e:
                        # 捕获流式请求的异常，但不立即返回错误
                        # 记录错误并继续尝试下一个API密钥
                        error_detail = handle_gemini_error(e, current_api_key, key_manager)
                        log('error', f"流式请求失败: {error_detail}",
                            extra={'key': current_api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                        # 不返回错误，而是抛出异常让外层循环处理
                        raise
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
    
    # 对于流式请求，创建一个特殊的StreamingResponse返回错误
    if chat_request.stream:
        async def error_generator():
            error_json = json.dumps({'error': {'message': msg, 'type': 'api_error'}})
            yield f"data: {error_json}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(error_generator(), media_type="text/event-stream")
    else:
        # 非流式请求使用标准HTTP异常
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)

# 流式请求处理函数
async def process_stream_request(
    chat_request: ChatCompletionRequest,
    http_request: Request,
    contents,
    system_instruction,
    current_api_key: str
) -> StreamingResponse:
    """处理流式API请求"""
    
    # 创建一个直接流式响应的生成器函数
    async def stream_response_generator():
        # 如果启用了假流式模式，使用随机遍历API密钥的方式
        if FAKE_STREAMING:
            # 创建一个队列用于在任务之间传递数据
            queue = asyncio.Queue()
            keep_alive_task = None
            api_request_task = None
            
            try:
                # 创建一个保持连接的任务，持续发送换行符
                async def keep_alive_sender():
                    try:
                        # 创建一个Gemini客户端用于发送保持连接的换行符
                        keep_alive_client = GeminiClient(current_api_key)
                        
                        # 启动保持连接的生成器
                        keep_alive_generator = keep_alive_client.stream_chat(
                            chat_request,
                            contents,
                            safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings,
                            system_instruction
                        )
                        
                        # 持续发送换行符直到被取消
                        async for line in keep_alive_generator:
                            if line == "\n":
                                # 将换行符格式化为SSE格式
                                formatted_chunk = {
                                    "id": "chatcmpl-keepalive",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": chat_request.model,
                                    "choices": [{"delta": {"content": ""}, "index": 0, "finish_reason": None}]
                                }
                                # 将格式化的换行符放入队列
                                await queue.put(f"data: {json.dumps(formatted_chunk)}\n\n")
                    except asyncio.CancelledError:
                        log('info', "保持连接任务被取消",
                            extra={'key': current_api_key[:8], 'request_type': 'fake-stream'})
                        raise
                    except Exception as e:
                        log('error', f"保持连接任务出错: {str(e)}",
                            extra={'key': current_api_key[:8], 'request_type': 'fake-stream'})
                        # 将错误放入队列
                        await queue.put(None)
                        raise
                
                # 创建一个任务来随机遍历API密钥并请求内容
                async def api_request_handler():
                    success = False
                    try:
                        # 重置已尝试的密钥
                        key_manager.reset_tried_keys_for_request()
                        
                        # 获取可用的API密钥
                        available_keys = key_manager.api_keys.copy()
                        random.shuffle(available_keys)  # 随机打乱密钥顺序
                        
                        # 遍历所有API密钥尝试获取响应
                        for attempt, api_key in enumerate(available_keys, 1):
                            try:
                                log('info', f"假流式模式: 尝试API密钥 {api_key[:8]}... ({attempt}/{len(available_keys)})",
                                    extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                                
                                # 创建一个新的客户端使用当前API密钥
                                non_stream_client = GeminiClient(api_key)
                                
                                # 使用非流式方式请求内容
                                response_content = await asyncio.to_thread(
                                    non_stream_client.complete_chat,
                                    chat_request,
                                    contents,
                                    safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings,
                                    system_instruction
                                )
                                
                                # 检查响应是否有效
                                if response_content and response_content.text:
                                    log('info', f"假流式模式: API密钥 {api_key[:8]}... 成功获取响应",
                                        extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                                    
                                    # 将完整响应分割成小块，模拟流式返回
                                    full_text = response_content.text
                                    chunk_size = max(len(full_text) // 10, 1)  # 至少分成10块，每块至少1个字符
                                    
                                    for i in range(0, len(full_text), chunk_size):
                                        chunk = full_text[i:i+chunk_size]
                                        formatted_chunk = {
                                            "id": "chatcmpl-someid",
                                            "object": "chat.completion.chunk",
                                            "created": int(time.time()),
                                            "model": chat_request.model,
                                            "choices": [{"delta": {"role": "assistant", "content": chunk}, "index": 0, "finish_reason": None}]
                                        }
                                        # 将格式化的内容块放入队列
                                        await queue.put(f"data: {json.dumps(formatted_chunk)}\n\n")
                                    
                                    success = True
                                    # 更新API调用统计
                                    from app.utils.stats import update_api_call_stats
                                    update_api_call_stats()
                                    break  # 成功获取响应，退出循环
                                else:
                                    log('warning', f"假流式模式: API密钥 {api_key[:8]}... 返回空响应",
                                        extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                            except Exception as e:
                                error_detail = handle_gemini_error(e, api_key, key_manager)
                                log('error', f"假流式模式: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                                    extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                                # 继续尝试下一个API密钥
                        
                        # 如果所有API密钥都尝试失败
                        if not success:
                            error_msg = "所有API密钥均请求失败，请稍后重试"
                            log('error', error_msg,
                                extra={'key': 'ALL', 'request_type': 'fake-stream', 'model': chat_request.model})
                            
                            # 添加错误信息到队列
                            error_json = {
                                "id": "chatcmpl-error",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": chat_request.model,
                                "choices": [{"delta": {"content": f"\n\n[错误: {error_msg}]"}, "index": 0, "finish_reason": "error"}]
                            }
                            await queue.put(f"data: {json.dumps(error_json)}\n\n")
                        
                        # 添加完成标记到队列
                        await queue.put("data: [DONE]\n\n")
                        # 添加None表示队列结束
                        await queue.put(None)
                        
                    except asyncio.CancelledError:
                        log('info', "API请求任务被取消",
                            extra={'key': current_api_key[:8], 'request_type': 'fake-stream'})
                        # 添加None表示队列结束
                        await queue.put(None)
                        raise
                    except Exception as e:
                        log('error', f"API请求任务出错: {str(e)}",
                            extra={'key': current_api_key[:8], 'request_type': 'fake-stream'})
                        # 添加错误信息到队列
                        error_json = {
                            "id": "chatcmpl-error",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": chat_request.model,
                            "choices": [{"delta": {"content": f"\n\n[错误: {str(e)}]"}, "index": 0, "finish_reason": "error"}]
                        }
                        await queue.put(f"data: {json.dumps(error_json)}\n\n")
                        await queue.put("data: [DONE]\n\n")
                        # 添加None表示队列结束
                        await queue.put(None)
                        raise
                
                # 启动保持连接的任务
                keep_alive_task = asyncio.create_task(keep_alive_sender())
                # 启动API请求任务
                api_request_task = asyncio.create_task(api_request_handler())
                
                # 从队列中获取数据并发送给客户端
                while True:
                    chunk = await queue.get()
                    if chunk is None:  # None表示队列结束
                        break
                    yield chunk
                    
                    # 如果API请求任务已完成，取消保持连接任务
                    if api_request_task.done() and not keep_alive_task.done():
                        keep_alive_task.cancel()
                
            except asyncio.CancelledError:
                log('info', "流式响应生成器被取消",
                    extra={'key': current_api_key[:8], 'request_type': 'fake-stream'})
                # 取消所有任务
                if keep_alive_task and not keep_alive_task.done():
                    keep_alive_task.cancel()
                if api_request_task and not api_request_task.done():
                    api_request_task.cancel()
            except Exception as e:
                log('error', f"流式响应生成器出错: {str(e)}",
                    extra={'key': current_api_key[:8], 'request_type': 'fake-stream'})
                # 取消所有任务
                if keep_alive_task and not keep_alive_task.done():
                    keep_alive_task.cancel()
                if api_request_task and not api_request_task.done():
                    api_request_task.cancel()
                # 发送错误信息给客户端
                error_json = {
                    "id": "chatcmpl-error",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": chat_request.model,
                    "choices": [{"delta": {"content": f"\n\n[错误: {str(e)}]"}, "index": 0, "finish_reason": "error"}]
                }
                yield f"data: {json.dumps(error_json)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                # 确保所有任务都被取消
                if keep_alive_task and not keep_alive_task.done():
                    keep_alive_task.cancel()
                if api_request_task and not api_request_task.done():
                    api_request_task.cancel()
        else:
            # 原始流式请求处理逻辑
            gemini_client = GeminiClient(current_api_key)
            success = False
            
            try:
                # 直接迭代生成器并发送响应块
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
                        "created": int(time.time()),
                        "model": chat_request.model,
                        "choices": [{"delta": {"role": "assistant", "content": chunk}, "index": 0, "finish_reason": None}]
                    }
                    success = True  # 只要有一个chunk成功，就标记为成功
                    yield f"data: {json.dumps(formatted_chunk)}\n\n"
                
                # 如果成功获取到响应，更新API调用统计
                if success:
                    from app.utils.stats import update_api_call_stats
                    update_api_call_stats()
                    
                yield "data: [DONE]\n\n"
                
            except asyncio.CancelledError:
                extra_log_cancel = {'key': current_api_key[:8], 'request_type': 'stream', 'model': chat_request.model, 'error_message': '客户端已断开连接'}
                log('info', "客户端连接已中断", extra=extra_log_cancel)
            except Exception as e:
                error_detail = handle_gemini_error(e, current_api_key, key_manager)
                log('error', f"流式请求失败: {error_detail}",
                    extra={'key': current_api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                # 发送错误信息给客户端
                error_json = {
                    "id": "chatcmpl-error",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": chat_request.model,
                    "choices": [{"delta": {"content": f"\n\n[错误: {error_detail}]"}, "index": 0, "finish_reason": "error"}]
                }
                yield f"data: {json.dumps(error_json)}\n\n"
                yield "data: [DONE]\n\n"
                # 重新抛出异常，这样process_request可以捕获它
                raise e
    
    return StreamingResponse(stream_response_generator(), media_type="text/event-stream")

# Gemini完成请求函数
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

# 客户端断开检测函数
async def check_client_disconnect(http_request: Request, current_api_key: str, request_type: str, model: str):
    """检查客户端是否断开连接"""
    while True:
        if await http_request.is_disconnected():
            extra_log = {'key': current_api_key[:8], 'request_type': request_type, 'model': model, 'error_message': '检测到客户端断开连接'}
            log('info', "客户端连接已中断，等待API请求完成", extra=extra_log)
            return True
        await asyncio.sleep(0.5)

# 客户端断开处理函数
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
        from app.utils.response import create_response
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
                from app.utils.response import create_response
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

# 非流式请求处理函数
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
            from app.utils.response import create_response
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
            from app.utils.response import create_response
            response = create_response(chat_request, response_content)
            
            # 不缓存这个响应，直接返回
            return response
        else:
            # 任务已完成，获取结果
            response_content = gemini_task.result()
            
            # 创建响应
            from app.utils.response import create_response
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