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

def openAI_stream_chunk(key, response):
    """
    根据 GeminiResponseWrapper 对象创建 OpenAI 流式标准响应对象块 (SSE 格式)。

    Args:
        key: 请求的唯一标识符 (UUID)。
        response: GeminiResponseWrapper 对象，包含响应数据。

    Returns:
        格式化后的 SSE 字符串 ("data: {...}\n\n")。
    """
    now_time = int(time.time())
    chunk_id = f"chatcmpl-{now_time}" # 使用时间戳生成唯一 ID 
    
    formatted_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": now_time,
        "model": response.model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": response.finish_reason}] 
    }

    if response.function_call:
        # 处理函数调用
        function_call_data = response.function_call
        function_name = function_call_data.get("name")
        # Gemini 的 args 是 dict, OpenAI 需要 string
        function_args_str = json.dumps(function_call_data.get("args", {}), ensure_ascii=False) 
        
        tool_call_id = f"{key}_{function_name}" # 编码函数名到 ID

        formatted_chunk["choices"][0]["delta"] = {
            "role": "assistant",
            "content": None, # 函数调用时 content 为 null
            "tool_calls": [
                {
                    "index": 0,
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": function_args_str,
                    }
                }
            ]
        }
        finish_reason = "tool_calls" # 函数调用时 finish_reason 为 tool_calls
    elif response.text:
        # 处理普通文本响应
        formatted_chunk["choices"][0]["delta"] = {"role": "assistant", "content": response.text}

    return f"data: {json.dumps(formatted_chunk)}\n\n"
