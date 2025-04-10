import asyncio
import json
import time
import random
from fastapi import Request
from fastapi.responses import StreamingResponse
from app.models import ChatCompletionRequest
from app.services import GeminiClient
from app.utils import handle_gemini_error, update_api_call_stats
from app.utils.logging import log

# 流式请求处理函数
async def process_stream_request(
    chat_request: ChatCompletionRequest,
    http_request: Request,
    contents,
    system_instruction,
    key_manager,
    safety_settings,
    safety_settings_g2,
    api_call_stats,
    FAKE_STREAMING,
    FAKE_STREAMING_INTERVAL
) -> StreamingResponse:
    """处理流式API请求"""
    
    # 创建一个直接流式响应的生成器函数
    async def stream_response_generator():
        # 重置已尝试的密钥
        key_manager.reset_tried_keys_for_request()
        
        # 获取可用的API密钥列表
        available_keys = key_manager.api_keys.copy()
        if FAKE_STREAMING:
            random.shuffle(available_keys)  # 假流式模式下随机打乱密钥顺序
        
        # 创建一个队列（用于假流式模式）
        queue = asyncio.Queue() if FAKE_STREAMING else None
        keep_alive_task = None
        response_task = None
        
        # 遍历所有API密钥尝试获取响应
        for attempt, api_key in enumerate(available_keys, 1):
            try:
                log('info', f"尝试API密钥 {api_key[:8]}... ({attempt}/{len(available_keys)})",
                    extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                
                if FAKE_STREAMING:
                    # 假流式模式的处理逻辑
                    try:
                        # 启动保持连接任务
                        keep_alive_task = asyncio.create_task(keep_alive_sender(api_key, queue, chat_request, contents, system_instruction, safety_settings, safety_settings_g2))
                        
                        # 创建一个任务来发送响应内容
                        async def send_response():
                            try:
                                # 使用非流式方式请求内容
                                non_stream_client = GeminiClient(api_key)
                                response_content = await asyncio.to_thread(
                                    non_stream_client.complete_chat,
                                    chat_request,
                                    contents,
                                    safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings,
                                    system_instruction
                                )
                                
                                # 处理响应内容
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
                                    
                                    # 更新API调用统计
                                    update_api_call_stats(api_call_stats, endpoint=api_key, model=chat_request.model)
                                    
                                    # 添加完成标记到队列
                                    await queue.put("data: [DONE]\n\n")
                                    # 添加None表示队列结束
                                    await queue.put(None)
                                    return True
                                else:
                                    log('warning', f"假流式模式: API密钥 {api_key[:8]}... 返回空响应，尝试下一个密钥",
                                        extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                                    return False
                            except Exception as e:
                                error_detail = handle_gemini_error(e, api_key, key_manager)
                                log('error', f"假流式模式: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                                    extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                                return False
                        
                        # 启动响应任务
                        response_task = asyncio.create_task(send_response())
                        
                        # 从队列中获取数据并发送给客户端
                        while True:
                            # 检查响应任务是否完成
                            if response_task and response_task.done():
                                success = response_task.result()
                                if success:
                                    # 成功获取响应，退出循环
                                    break
                                else:
                                    # 响应失败，继续尝试下一个API密钥
                                    break
                            
                            # 从队列中获取数据
                            try:
                                # 设置超时，以便定期检查响应任务状态
                                chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
                                if chunk is None:  # None表示队列结束
                                    break
                                yield chunk
                            except asyncio.TimeoutError:
                                # 超时，继续循环
                                continue
                        
                        # 如果响应任务成功，退出循环
                        if response_task and response_task.done() and response_task.result():
                            return
                    except Exception as e:
                        error_detail = handle_gemini_error(e, api_key, key_manager)
                        log('error', f"假流式模式: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                            extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                        # 继续尝试下一个API密钥
                    finally:
                        if keep_alive_task and not keep_alive_task.done():
                            keep_alive_task.cancel()
                        if response_task and not response_task.done():
                            response_task.cancel()
                else:
                    # 原始流式模式的处理逻辑
                    gemini_client = GeminiClient(api_key)
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
                            update_api_call_stats(api_call_stats, endpoint=api_key, model=chat_request.model)
                            
                        yield "data: [DONE]\n\n"
                        return  # 成功获取响应，退出循环
                        
                    except asyncio.CancelledError:
                        log('info', "客户端连接已中断", 
                            extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                        raise
                    except Exception as e:
                        error_detail = handle_gemini_error(e, api_key, key_manager)
                        log('error', f"流式请求失败: {error_detail}",
                            extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                        # 继续尝试下一个API密钥
                        continue
            
            except asyncio.CancelledError:
                # 客户端连接中断，直接抛出异常
                raise
            except Exception as e:
                # 其他异常，继续尝试下一个API密钥
                continue
        
        # 所有API密钥都尝试失败的处理
        error_msg = "所有API密钥均请求失败，请稍后重试"
        log('error', error_msg,
            extra={'key': 'ALL', 'request_type': 'stream', 'model': chat_request.model})
        
        # 发送错误信息给客户端
        error_json = {
            "id": "chatcmpl-error",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": chat_request.model,
            "choices": [{"delta": {"content": f"\n\n[错误: {error_msg}]"}, "index": 0, "finish_reason": "error"}]
        }
        yield f"data: {json.dumps(error_json)}\n\n"
        yield "data: [DONE]\n\n"
    
    # 保持连接的任务
    async def keep_alive_sender(api_key, queue, chat_request, contents, system_instruction, safety_settings, safety_settings_g2):
        try:
            # 创建一个Gemini客户端用于发送保持连接的换行符
            keep_alive_client = GeminiClient(api_key)
            
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
            raise
        except Exception as e:
            log('error', f"保持连接任务出错: {str(e)}",
                extra={'key': api_key[:8], 'request_type': 'fake-stream'})
            # 将错误放入队列
            await queue.put(None)
            raise
    
    return StreamingResponse(stream_response_generator(), media_type="text/event-stream")