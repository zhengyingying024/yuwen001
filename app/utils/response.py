import time

def create_complete_response(response):
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
