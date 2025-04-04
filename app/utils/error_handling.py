import requests
import logging
import asyncio
from fastapi import HTTPException, status
from app.utils.logging import format_log_message

logger = logging.getLogger("my_logger")

def handle_gemini_error(error, current_api_key, key_manager) -> str:
    if isinstance(error, requests.exceptions.HTTPError):
        status_code = error.response.status_code
        if status_code == 400:
            try:
                error_data = error.response.json()
                if 'error' in error_data:
                    if error_data['error'].get('code') == "invalid_argument":
                        error_message = "无效的 API 密钥"
                        extra_log_invalid_key = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
                        log_msg = format_log_message('ERROR', f"{current_api_key[:8]} ... {current_api_key[-3:]} → 无效，可能已过期或被删除", extra=extra_log_invalid_key)
                        logger.error(log_msg)
                        # key_manager.blacklist_key(current_api_key)
                        
                        return error_message
                    error_message = error_data['error'].get(
                        'message', 'Bad Request')
                    extra_log_400 = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
                    log_msg = format_log_message('WARNING', f"400 错误请求: {error_message}", extra=extra_log_400)
                    logger.warning(log_msg)
                    return f"400 错误请求: {error_message}"
            except ValueError:
                error_message = "400 错误请求：响应不是有效的JSON格式"
                extra_log_400_json = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
                log_msg = format_log_message('WARNING', error_message, extra=extra_log_400_json)
                logger.warning(log_msg)
                return error_message

        elif status_code == 429:
            error_message = "API 密钥配额已用尽或其他原因"
            extra_log_429 = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
            log_msg = format_log_message('WARNING', f"{current_api_key[:8]} ... {current_api_key[-3:]} → 429 官方资源耗尽或其他原因", extra=extra_log_429)
            logger.warning(log_msg)
            # key_manager.blacklist_key(current_api_key)
             
            return error_message

        elif status_code == 403:
            error_message = "权限被拒绝"
            extra_log_403 = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
            log_msg = format_log_message('ERROR', f"{current_api_key[:8]} ... {current_api_key[-3:]} → 403 权限被拒绝", extra=extra_log_403)
            logger.error(log_msg)
            # key_manager.blacklist_key(current_api_key)
            
            return error_message
        elif status_code == 500:
            error_message = "服务器内部错误"
            extra_log_500 = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
            log_msg = format_log_message('WARNING', f"{current_api_key[:8]} ... {current_api_key[-3:]} → 500 服务器内部错误", extra=extra_log_500)
            logger.warning(log_msg)
            
            return "Gemini API 内部错误"

        elif status_code == 503:
            error_message = "服务不可用"
            extra_log_503 = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
            log_msg = format_log_message('WARNING', f"{current_api_key[:8]} ... {current_api_key[-3:]} → 503 服务不可用", extra=extra_log_503)
            logger.warning(log_msg)
            
            return "Gemini API 服务不可用"
        else:
            error_message = f"未知错误: {status_code}"
            extra_log_other = {'key': current_api_key[:8], 'status_code': status_code, 'error_message': error_message}
            log_msg = format_log_message('WARNING', f"{current_api_key[:8]} ... {current_api_key[-3:]} → {status_code} 未知错误", extra=extra_log_other)
            logger.warning(log_msg)
            
            return f"未知错误/模型不可用: {status_code}"

    elif isinstance(error, requests.exceptions.ConnectionError):
        error_message = "连接错误"
        log_msg = format_log_message('WARNING', error_message, extra={'error_message': error_message})
        logger.warning(log_msg)
        return error_message

    elif isinstance(error, requests.exceptions.Timeout):
        error_message = "请求超时"
        log_msg = format_log_message('WARNING', error_message, extra={'error_message': error_message})
        logger.warning(log_msg)
        return error_message
    else:
        error_message = f"发生未知错误: {error}"
        log_msg = format_log_message('ERROR', error_message, extra={'error_message': error_message})
        logger.error(log_msg)
        return error_message

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

async def handle_api_error(e, api_key, key_manager, request_type, model, retry_count=0):
    """统一处理API错误，对500和503错误实现自动重试机制"""
    error_detail = handle_gemini_error(e, api_key, key_manager)
    
    # 处理500和503服务器错误
    if isinstance(e, requests.exceptions.HTTPError) and ('500' in str(e) or '503' in str(e)):
        status_code = '500' if '500' in str(e) else '503'
        
        # 最多重试3次
        if retry_count < 3:
            wait_time = min(1 * (2 ** retry_count), 16)  # RETRY_DELAY=1, MAX_RETRY_DELAY=16
            log_msg = format_log_message('WARNING', f"Gemini服务器错误({status_code})，等待{wait_time}秒后重试 ({retry_count+1}/3)",
                extra={'key': api_key[:8], 'request_type': request_type, 'model': model, 'status_code': int(status_code)})
            logger.warning(log_msg)
            
            # 等待后返回重试信号
            await asyncio.sleep(wait_time)
            return {'should_retry': True, 'error': error_detail, 'remove_cache': False}
        
        # 重试次数用尽，直接返回错误状态码
        log_msg = format_log_message('ERROR', f"服务器错误({status_code})重试{retry_count}次后仍然失败",
            extra={'key': api_key[:8], 'request_type': request_type, 'model': model, 'status_code': int(status_code)})
        logger.error(log_msg)
        
        # 不建议切换密钥，直接抛出HTTP异常
        raise HTTPException(status_code=int(status_code),
                          detail=f"Gemini API 服务器错误({status_code})，请稍后重试")
    
    # 对于其他错误，返回切换密钥的信号
    log_msg = format_log_message('ERROR', f"API错误: {error_detail}",
        extra={'key': api_key[:8], 'request_type': request_type, 'model': model, 'error_message': error_detail})
    logger.error(log_msg)
    return {'should_retry': False, 'should_switch_key': True, 'error': error_detail, 'remove_cache': True}