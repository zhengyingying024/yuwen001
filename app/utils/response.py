import json
import time

def openAI_nonstream_response(response):
    """
    使用 gemini 非流式响应对象(提取后),
    创建 OpenAI 非流式标准响应对象
    """
    return {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response.model,
        "choices": [{
            "index": 0, 
            "message": {
                "role": "assistant", 
                "content": response.text
            }, 
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": response.prompt_token_count,
            "completion_tokens": response.candidates_token_count,
            "total_tokens": response.total_token_count
        }
    }

def openAI_stream_chunk(model="gemini",content=None,finish_reason=None,total_token_count=0):
    """
    创建 OpenAI 流式标准响应对象块 (SSE 格式)
    """
    
    now_time = int(time.time())
    if finish_reason:
        
        formatted_chunk = {
            "id": f"chatcmpl-{now_time}",
            "object": "chat.completion.chunk",
            "created": now_time,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": finish_reason}]
        }
    
    else:
        formatted_chunk = {
            "id": f"chatcmpl-{now_time}",
            "object": "chat.completion.chunk",
            "created": now_time,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
            "usage": {
                "total_tokens": total_token_count
            }
            
        }
    
    return f"data: {json.dumps(formatted_chunk)}\n\n"
    