import asyncio
from app.models import ChatCompletionRequest
from app.services import GeminiClient
from .logging_utils import log

# Gemini完成请求函数
async def run_gemini_completion(
    gemini_client, 
    chat_request: ChatCompletionRequest, 
    contents,
    system_instruction,
    request_type: str,
    current_api_key: str,
    safety_settings,
    safety_settings_g2
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