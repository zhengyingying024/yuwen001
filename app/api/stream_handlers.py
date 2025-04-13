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
from app.config.settings import CONCURRENT_REQUESTS, INCREASE_CONCURRENT_ON_FAILURE, MAX_CONCURRENT_REQUESTS

# 流式请求处理函数
async def process_stream_request(
    chat_request: ChatCompletionRequest,
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
        # 转换消息格式
        contents, system_instruction = GeminiClient.convert_messages(
        GeminiClient, chat_request.messages,model=chat_request.model)

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
        
        # 创建一个队列（用于假流式模式的响应内容）
        response_queue = asyncio.Queue() if FAKE_STREAMING else None
        
        # 用于跟踪保活是否应该继续的标志
        keep_alive_running = True
        
        # 定义保活发送函数
        async def keep_alive_sender():
            try:
                while keep_alive_running:
                    yield "\n"
                    # 等待一段时间再发送下一个保活消息
                    await asyncio.sleep(FAKE_STREAMING_INTERVAL)
            except asyncio.CancelledError:
                log('info', "假流式模式: 保活任务被取消",
                    extra={'request_type': 'fake-stream', 'model': chat_request.model})
                raise
            except Exception as e:
                log('error', f"保活任务出错: {str(e)}",
                    extra={'request_type': 'fake-stream'})
                raise
        
        # 创建保活生成器
        keep_alive_gen = keep_alive_sender() if FAKE_STREAMING else None
        
        # 如果是假流式模式，先发送一次保活消息,以免处理时断联
        if FAKE_STREAMING :
            yield "\n"
        
        # (假流式) 尝试使用不同API密钥，直到所有密钥都尝试过
        while (all_keys and FAKE_STREAMING):
            # 获取当前批次的密钥
            current_batch = all_keys[:current_concurrent]
            all_keys = all_keys[current_concurrent:]
            
            # 创建并发任务
            tasks = []
            for api_key in current_batch:
                # 假流式模式的处理逻辑
                log('info', f"假流式请求开始，使用密钥: {api_key[:8]}...",
                extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                task = asyncio.create_task(
                    handle_fake_streaming(
                        api_key, 
                        response_queue,  # 使用响应队列
                        chat_request, 
                        contents, 
                        system_instruction, 
                        safety_settings, 
                        safety_settings_g2,
                        api_call_stats
                    )
                )

                tasks.append((api_key, task))
            
            # 等待第一个成功的响应或超时
            while tasks and not all(t[1].done() for t in tasks):
                # 短时间等待任务完成
                done, pending = await asyncio.wait(
                    [task for _, task in tasks],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # 如果没有任务完成且是假流式模式，发送保活消息
                if not done and FAKE_STREAMING and keep_alive_gen:
                    try:
                        keepalive = await anext(keep_alive_gen)
                        yield keepalive
                    except StopAsyncIteration:
                        break
                
                # 如果有任务完成，跳出循环
                if done:
                    break
            
            # # 取消所有未完成的任务
            # for _, task in tasks:
            #     if not task.done():
            #         task.cancel()
            
            # 检查是否有成功的响应
            success = False
            for api_key, task in tasks:
                if task.done() and not task.cancelled():
                    try:
                        result = task.result()
                        if result:  # 如果有响应内容
                            success = True
                            
                            # 停止保活机制
                            keep_alive_running = False
                            # 如果保活生成器存在，需要关闭它
                            if keep_alive_gen:
                                keep_alive_gen.aclose()
                            
                            # 从队列中获取响应数据
                            while True:
                                chunk = await response_queue.get()
                                if chunk is None:  # None表示队列结束
                                    break
                                if chunk == "data: [DONE]\n\n":  # 完成标记
                                    yield chunk
                                    break
                                # 确保chunk符合SSE格式
                                if not chunk.endswith("\n\n"):
                                    chunk = chunk.rstrip() + "\n\n"
                                yield chunk
                            log('info', f"假流式成功响应，使用密钥: {api_key[:8]}...", 
                                extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})                                
                            return  # 成功获取响应，退出循环
                    except Exception as e:
                        error_detail = handle_gemini_error(e, api_key, key_manager)
                        log('error', f"请求失败: {error_detail}",
                            extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})                        
            
            # 如果所有请求都失败，增加并发数并继续尝试
            if not success and all_keys:
                # 增加并发数，但不超过最大并发数
                current_concurrent = min(current_concurrent + INCREASE_CONCURRENT_ON_FAILURE, MAX_CONCURRENT_REQUESTS)
                log('info', f"所有请求失败，增加并发数至: {current_concurrent}", 
                    extra={'request_type': 'stream', 'model': chat_request.model})

        # (真流式) 尝试使用不同API密钥，直到所有密钥都尝试过
        while (all_keys and not FAKE_STREAMING):
            # 获取密钥
            api_key = all_keys[0]
            all_keys = all_keys[1:]                                  

            success = False
            try:            
                gemini_client = GeminiClient(api_key)
                
                # 获取流式响应
                stream_generator = gemini_client.stream_chat(
                    chat_request,
                    contents,
                    safety_settings_g2 if 'gemini-2.0-flash-exp' in chat_request.model else safety_settings,
                    system_instruction
                )
                
                # 处理流式响应
                async for chunk in stream_generator:                    
                    if chunk or success:                    
                        success = True
                        formatted_chunk = {
                            "id": "chatcmpl-someid",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": chat_request.model,
                            "choices": [{"delta": {"role": "assistant", "content": chunk}, "index": 0, "finish_reason": None}]
                        }
                        yield f"data: {json.dumps(formatted_chunk)}\n\n"
                    else:
                        log('warning', f"流式响应: API密钥 {api_key[:8]}... 返回空响应",
                            extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                        break
            except Exception as e:
                error_detail = handle_gemini_error(e, api_key, key_manager)
                log('error', f"流式响应: API密钥 {api_key[:8]}... 请求失败: {error_detail}",
                    extra={'key': api_key[:8], 'request_type': 'stream', 'model': chat_request.model})
                return
            finally:
                # 更新API调用统计
                if success:
                    update_api_call_stats(api_call_stats, endpoint=api_key, model=chat_request.model)
                    return
                                                
        # 所有API密钥都尝试失败的处理
        error_msg = "所有API密钥均请求失败，请稍后重试"
        log('error', error_msg,
            extra={'key': 'ALL', 'request_type': 'stream', 'model': chat_request.model})
        
        # (?为什么发送SSE而不是报错异常？)发送错误信息给客户端
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
    async def handle_fake_streaming(api_key, response_queue, chat_request, contents, system_instruction, safety_settings, safety_settings_g2, api_call_stats):
        try:
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
                        # log('info', f"假流式模式: API密钥 {api_key[:8]}... 成功获取响应",
                        #     extra={'key': api_key[:8], 'request_type': 'fake-stream', 'model': chat_request.model})
                        
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
                                "choices": [{"delta": {"content": chunk}, "index": 0, "finish_reason": None}]
                            }
                            # 将格式化的内容块放入响应队列
                            formatted_data = f"data: {json.dumps(formatted_chunk, ensure_ascii=False)}\n\n"
                            await response_queue.put(formatted_data)
                        
                        # 更新API调用统计
                        update_api_call_stats(api_call_stats, endpoint=api_key, model=chat_request.model)
                        
                        # 添加完成标记到队列
                        await response_queue.put("data: [DONE]\n\n")
                        # 添加None表示队列结束
                        await response_queue.put(None)
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
    
    return StreamingResponse(stream_response_generator(), media_type="text/event-stream")