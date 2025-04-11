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
    FAKE_STREAMING_INTERVAL,
    CONCURRENT_REQUESTS,
    INCREASE_CONCURRENT_ON_FAILURE,
    MAX_CONCURRENT_REQUESTS
) -> StreamingResponse:
    """处理流式API请求"""
    
    # 创建一个直接流式响应的生成器函数
    async def stream_response_generator():
        # 重置已尝试的密钥
        key_manager.reset_tried_keys_for_request()
        
        # 获取所有可用的API密钥
        all_keys = key_manager.api_keys.copy()
        random.shuffle(all_keys)  # 随机打乱密钥顺序
        
        # 设置初始并发数
        current_concurrent = CONCURRENT_REQUESTS
        
        # 如果可用密钥数量小于并发数，则使用所有可用密钥
        if len(all_keys) < current_concurrent:
            current_concurrent = len(all_keys)
        
        # 创建一个队列（用于假流式模式）
        queue = asyncio.Queue() if FAKE_STREAMING else None
        
        # 尝试使用不同API密钥，直到所有密钥都尝试过
        while all_keys:
            # 获取当前批次的密钥
            current_batch = all_keys[:current_concurrent]
            all_keys = all_keys[current_concurrent:]
            
            # 创建并发任务
            tasks = []
            for api_key in current_batch:
                log('info', f"并发流式请求使用密钥: {api_key[:8]}...",
                    extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                
                if FAKE_STREAMING:
                    # 假流式模式的处理逻辑
                    task = asyncio.create_task(
                        handle_fake_streaming(
                            api_key, 
                            queue, 
                            chat_request, 
                            contents, 
                            system_instruction, 
                            safety_settings, 
                            safety_settings_g2,
                            api_call_stats
                        )
                    )
                else:
                    # 原始流式模式的处理逻辑
                    task = asyncio.create_task(
                        handle_real_streaming(
                            api_key, 
                            chat_request, 
                            contents, 
                            system_instruction, 
                            safety_settings, 
                            safety_settings_g2,
                            api_call_stats
                        )
                    )
                tasks.append((api_key, task))
            
            # 等待第一个成功的响应
            done, pending = await asyncio.wait(
                [task for _, task in tasks],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消所有未完成的任务
            for _, task in tasks:
                if not task.done():
                    task.cancel()
            
            # 检查是否有成功的响应
            success = False
            for api_key, task in tasks:
                if task in done:
                    try:
                        result = task.result()
                        if result:  # 如果有响应内容
                            success = True
                            log('info', f"并发流式请求成功，使用密钥: {api_key[:8]}...", 
                                extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                            
                            # 如果是假流式模式，从队列中获取数据
                            if FAKE_STREAMING:
                                while True:
                                    chunk = await queue.get()
                                    if chunk is None:  # None表示队列结束
                                        break
                                    yield chunk
                            else:
                                # 直接迭代生成器并发送响应块
                                async for chunk in result:
                                    yield chunk
                            
                            return  # 成功获取响应，退出循环
                    except Exception as e:
                        error_detail = handle_gemini_error(e, api_key, key_manager)
                        log('error', f"并发流式请求失败: {error_detail}",
                            extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
            
            # 如果所有请求都失败，增加并发数并继续尝试
            if not success and all_keys:
                # 增加并发数，但不超过最大并发数
                current_concurrent = min(current_concurrent + INCREASE_CONCURRENT_ON_FAILURE, MAX_CONCURRENT_REQUESTS)
                log('info', f"所有并发流式请求失败，增加并发数至: {current_concurrent}", 
                    extra={'request_type': 'stream', 'model': chat_request.model})
        
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
    
    # 处理假流式模式
    async def handle_fake_streaming(api_key, queue, chat_request, contents, system_instruction, safety_settings, safety_settings_g2, api_call_stats):
        try:
            # 创建保持连接的任务
            keep_alive_task = None
            response_task = None
            
            try:
                # 启动保持连接任务
                keep_alive_task = asyncio.create_task(
                    keep_alive_sender(
                        api_key, 
                        queue, 
                        chat_request, 
                        contents, 
                        system_instruction, 
                        safety_settings, 
                        safety_settings_g2
                    )
                )
                
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
                            chunk_size = max(len(full_text) // 10, 1)  # 分成10块
                            
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
                            log('warning', f"假流式模式: API密钥 {api_key[:8]}... 返回空响应",
                                extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                            return False
                    except Exception as e:
                        error_detail = handle_gemini_error(e, api_key, key_manager)
                        log('error', f"假流式模式: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                            extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                        return False
                
                # 启动响应任务
                response_task = asyncio.create_task(send_response())
                
                # 等待响应任务完成
                success = await response_task
                return success
                
            except Exception as e:
                error_detail = handle_gemini_error(e, api_key, key_manager)
                log('error', f"假流式模式: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                    extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                return False
            finally:
                # 取消保持连接任务
                if keep_alive_task and not keep_alive_task.done():
                    keep_alive_task.cancel()
                # 取消响应任务
                if response_task and not response_task.done():
                    response_task.cancel()
        except Exception as e:
            error_detail = handle_gemini_error(e, api_key, key_manager)
            log('error', f"假流式模式: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
            return False
    
    # 保持连接的任务
    async def keep_alive_sender(api_key, queue, chat_request, contents, system_instruction, safety_settings, safety_settings_g2):
        try:
            # 使用定时器主动发送换行符，而不是依赖生成器返回的换行符
            while True:
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
                
                # 等待一段时间再发送下一个换行符
                await asyncio.sleep(FAKE_STREAMING_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log('error', f"保持连接任务出错: {str(e)}",
                extra={'key': api_key[:8], 'request_type': 'fake-stream'})
            # 将错误放入队列
            await queue.put(None)
            raise
    
    # 处理真实流式模式
    async def handle_real_streaming(api_key, chat_request, contents, system_instruction, safety_settings, safety_settings_g2, api_call_stats):
        try:
            # 创建Gemini客户端
            gemini_client = GeminiClient(api_key)
            
            # 获取流式响应
            stream_generator = gemini_client.stream_chat(
                chat_request,
                contents,
                safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings,
                system_instruction
            )
            
            # 检查是否有内容
            has_content = False
            async for chunk in stream_generator:
                if chunk:
                    has_content = True
                    break
            
            if has_content:
                # 更新API调用统计
                update_api_call_stats(api_call_stats, endpoint=api_key, model=chat_request.model)
                
                # 重新创建流式生成器
                return gemini_client.stream_chat(
                    chat_request,
                    contents,
                    safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings,
                    system_instruction
                )
            else:
                log('warning', f"真实流式模式: API密钥 {api_key[:8]}... 返回空响应",
                    extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                return None
        except Exception as e:
            error_detail = handle_gemini_error(e, api_key, key_manager)
            log('error', f"真实流式模式: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
            return None
    
    return StreamingResponse(stream_response_generator(), media_type="text/event-stream")