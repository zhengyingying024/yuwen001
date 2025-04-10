import asyncio
import json
from typing import Literal
from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from app.models import ChatCompletionRequest
from app.services import GeminiClient
from app.utils import protect_from_abuse, handle_gemini_error, handle_api_error
from app.utils.logging import log
from .stream_handlers import process_stream_request
from .nonstream_handlers import process_nonstream_request

# 请求处理函数
async def process_request(
    chat_request: ChatCompletionRequest, 
    http_request: Request, 
    request_type: Literal['stream', 'non-stream'], 
    key_manager,
    response_cache_manager,
    active_requests_manager,
    safety_settings,
    safety_settings_g2,
    api_call_stats,
    FAKE_STREAMING,
    FAKE_STREAMING_INTERVAL,
    MAX_REQUESTS_PER_MINUTE,
    MAX_REQUESTS_PER_DAY_PER_IP,
    cache_key: str = None, 
    client_ip: str = None
):
    """处理API请求的主函数，根据需要处理流式或非流式请求"""
    global current_api_key
    
    # 请求前基本检查
    protect_from_abuse(
        http_request, MAX_REQUESTS_PER_MINUTE, MAX_REQUESTS_PER_DAY_PER_IP)
    if chat_request.model not in GeminiClient.AVAILABLE_MODELS:
        log('error', "无效的模型", 
            extra={'request_type': request_type, 'model': chat_request.model, 'status_code': 400})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="无效的模型")

    # 重置已尝试的密钥
    key_manager.reset_tried_keys_for_request()
    # 转换消息格式
    contents, system_instruction = GeminiClient.convert_messages(
        GeminiClient, chat_request.messages,model=chat_request.model)

    # 设置重试次数（使用可用API密钥数量作为最大重试次数）
    retry_attempts = len(key_manager.api_keys) if key_manager.api_keys else 1
    
    # 尝试使用不同API密钥
    for attempt in range(1, retry_attempts + 1):
        # 获取密钥
        current_api_key = key_manager.get_available_key()
        
        # 检查API密钥是否可用
        if current_api_key is None:
            log('warning', "没有可用的 API 密钥，跳过本次尝试", 
                extra={'request_type': request_type, 'model': chat_request.model})
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
                            current_api_key,
                            key_manager,
                            safety_settings,
                            safety_settings_g2,
                            api_call_stats,
                            FAKE_STREAMING,
                            FAKE_STREAMING_INTERVAL
                        )
                    except Exception as e:
                        # 捕获流式请求的异常，但不立即返回错误，而是抛出异常让外层循环处理
                        # 记录错误并继续尝试下一个API密钥
                        error_detail = handle_gemini_error(e, current_api_key, key_manager)
                        log('info', f"流式请求失败: {error_detail}",
                            extra={'key': current_api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                        raise
                else:
                    return await process_nonstream_request(
                        chat_request,
                        http_request,
                        request_type,
                        contents,
                        system_instruction,
                        current_api_key,
                        response_cache_manager,
                        active_requests_manager,
                        safety_settings,
                        safety_settings_g2,
                        api_call_stats,
                        cache_key,
                        client_ip
                    )
            except HTTPException as e:
                if e.status_code == status.HTTP_408_REQUEST_TIMEOUT:
                    log('info', "客户端连接中断", 
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
                
                else:
                    # 跳出循环
                    break

    # 如果所有尝试都失败
    msg = "所有API密钥均请求失败,请稍后重试"
    log('error', "API key 替换失败，所有API key都已尝试，请重新配置或稍后重试", extra={'request_type': 'switch_key'})
    
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