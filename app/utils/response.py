import time
from fastapi import status
from fastapi.responses import JSONResponse

def create_chat_response(model: str, choices: list, id: str = None):
    """创建标准响应对象的工厂函数"""
    return {
        "id": id or f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }

def create_error_response(model: str, error_message: str):
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

def create_response(chat_request, response_content):
    """创建标准响应对象"""
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

def handle_exception(exc_type, exc_value, exc_traceback, translate_error, log):
    """处理全局异常的函数"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 对于KeyboardInterrupt，使用默认处理
        import sys
        sys.excepthook(exc_type, exc_value, exc_traceback)
        return
    
    # 对于其他异常，记录日志
    error_message = translate_error(str(exc_value))
    log('error', f"未捕获的异常: {error_message}", status_code=500, error_message=error_message)