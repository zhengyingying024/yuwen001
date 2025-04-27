import requests
import json
import os
import asyncio
import time
from app.models import ChatCompletionRequest, Message
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import httpx
import logging
import secrets
import string
from app.utils import format_log_message
import app.config.settings as settings

from app.utils.logging import log

def generate_secure_random_string(length):
    all_characters = string.ascii_letters + string.digits
    secure_random_string = ''.join(secrets.choice(all_characters) for _ in range(length))
    return secure_random_string

logger = logging.getLogger('my_logger')

@dataclass
class GeneratedText:
    text: str
    finish_reason: Optional[str] = None


class ResponseWrapper:
    def __init__(self, data: Dict[Any, Any]):  
        self._data = data
        self._text = self._extract_text()
        self._finish_reason = self._extract_finish_reason()
        self._prompt_token_count = self._extract_prompt_token_count()
        self._candidates_token_count = self._extract_candidates_token_count()
        self._total_token_count = self._extract_total_token_count()
        self._thoughts = self._extract_thoughts()
        self._json_dumps = json.dumps(self._data, indent=4, ensure_ascii=False)
        self._model = "gemini"

    def _extract_thoughts(self) -> Optional[str]:
        try:
            for part in self._data['candidates'][0]['content']['parts']:
                if 'thought' in part:
                    return part['text']
            return ""
        except (KeyError, IndexError):
            return ""

    def _extract_text(self) -> str:
        try:
            text=""
            for part in self._data['candidates'][0]['content']['parts']:
                if 'thought' not in part:
                    text+=part['text']
            return text
        except (KeyError, IndexError):
            return ""

    def _extract_finish_reason(self) -> Optional[str]:
        try:
            return self._data['candidates'][0].get('finishReason')
        except (KeyError, IndexError):
            return None

    def _extract_prompt_token_count(self) -> Optional[int]:
        try:
            return self._data['usageMetadata'].get('promptTokenCount')
        except (KeyError):
            return None

    def _extract_candidates_token_count(self) -> Optional[int]:
        try:
            return self._data['usageMetadata'].get('candidatesTokenCount')
        except (KeyError):
            return None

    def _extract_total_token_count(self) -> Optional[int]:
        try:
            return self._data['usageMetadata'].get('totalTokenCount')
        except (KeyError):
            return None

    def set_model(self,model) -> Optional[str]:
        self._model = model

    @property
    def text(self) -> str:
        return self._text

    @property
    def finish_reason(self) -> Optional[str]:
        return self._finish_reason

    @property
    def prompt_token_count(self) -> Optional[int]:
        return self._prompt_token_count

    @property
    def candidates_token_count(self) -> Optional[int]:
        return self._candidates_token_count

    @property
    def total_token_count(self) -> Optional[int]:
        return self._total_token_count

    @property
    def thoughts(self) -> Optional[str]:
        return self._thoughts

    @property
    def json_dumps(self) -> str:
        return self._json_dumps

    @property
    def model(self) -> str:
        return self._model


class GeminiClient:

    AVAILABLE_MODELS = []
    EXTRA_MODELS = os.environ.get("EXTRA_MODELS", "").split(",")

    def __init__(self, api_key: str):
        self.api_key = api_key

    # 请求参数处理
    def _prepare_request_data(self, request, contents, safety_settings, system_instruction,model):
        api_version = "v1alpha" if "think" in request.model else "v1beta"
        if settings.search["search_mode"] and model.endswith("-search"):
            extra_log={'key': self.api_key[:8], 'model':model}
            log('INFO', "开启联网搜索模式", extra=extra_log)
            data = {
                "contents": contents,
                "tools": [{"google_search": {}}],
                "generationConfig": self._get_generation_config(request),
                "safetySettings": safety_settings,
            }
        else:
            data = {
                "contents": contents,
                "generationConfig": self._get_generation_config(request),
                "safetySettings": safety_settings,
            }
        if system_instruction:
            data["system_instruction"] = system_instruction
        return api_version, data
    
    def _get_generation_config(self, request):
        config_params = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
            "topP": request.top_p,
            "topK": request.top_k,
            "stopSequences": request.stop if isinstance(request.stop, list) else [request.stop] if request.stop is not None else None,
            "candidateCount": request.n,
        }
        if request.thinking_budget:
            config_params["thinkingConfig"] = {
                "thinkingBudget": request.thinking_budget
            }
        return {k: v for k, v in config_params.items() if v is not None}

    # 假流式保活处理 (未完成，所以未使用)
    async def keep_alive_sender(self, request: ChatCompletionRequest):
        extra_log={'key': self.api_key[:8], 'request_type': 'fake_stream', 'model': request.model}
        log('INFO', "使用假流式请求模式（发送换行符保持连接）", extra=extra_log)
        try:
            
            # 每隔一段时间发送换行符作为保活消息，直到外部取消此生成器
            start_time = time.time()
            while True:
                yield "\n"
                await asyncio.sleep(settings.FAKE_STREAMING_INTERVAL)
                
                # 如果等待时间过长（超过300秒），抛出超时异常，让外部处理
                if time.time() - start_time > 300:
                    log('ERROR', f"假流式请求等待时间过长",extra=extra_log)
                    
                    raise TimeoutError("假流式请求等待时间过长")
            
        except Exception as e:
            if not isinstance(e, asyncio.CancelledError):  
                log('ERROR', f"假流式处理期间发生错误: {str(e)}", extra=extra_log)
            raise e
        finally:
            log('INFO', "假流式请求结束", extra=extra_log)

    # 解析单个 SSE 数据块
    def _parse_sse_chunk(self, chunk_data: dict) -> Optional[Dict[str, Any]]:
        """
        解析从 Gemini API 返回的单个 SSE JSON 数据块。

        Args:
            chunk_data: 从 SSE 消息中解析出的 JSON 对象。

        Returns:
            一个字典，包含解析后的信息 (type, content, token, reason)，
            如果无法解析或块无效，则返回 None。
        """
        try:
            # 提取 token 计数 (如果存在)
            token = chunk_data.get('usageMetadata', {}).get('totalTokenCount')

            # 检查 candidates 是否存在且非空
            if not chunk_data.get('candidates'):
                # 可能是只有 usageMetadata 的块，或者其他类型的块，暂时忽略
                return None # 或者返回一个表示 metadata 的类型

            candidate = chunk_data['candidates'][0]
            content = candidate.get('content')
            finish_reason = candidate.get('finishReason')

            # 检查安全评级 - 如果被阻止，视为错误并抛出
            if 'safetyRatings' in candidate:
                for rating in candidate['safetyRatings']:
                    if rating.get('blocked'): # 检查是否被阻止
                        category = rating.get('category', 'UNKNOWN')
                        error_msg = f"响应因安全原因被阻止: 类别 {category}"
                        # 此处直接抛出异常，让 stream_chat 中的外层 try-except 处理
                        raise ValueError(error_msg) 

            # 检查是否有内容部分
            if content and content.get('parts'):
                parts = content['parts']
                text_content = ""
                function_call_content = None
                for part in parts:
                    if 'text' in part:
                        text_content += part['text']
                    elif 'functionCall' in part:
                        # 假设一个块中只有一个 functionCall
                        function_call_content = part['functionCall']
                        # 通常 functionCall 后没有 text，如果需要处理混合，逻辑需调整
                        break 
                
                if function_call_content:
                    # 发现函数调用
                    return {'type': 'function_call', 'content': function_call_content, 'token': token}
                elif finish_reason:
                    # 如果有完成原因，这通常是流的最后一个有效信息块
                    # Gemini 可能的 finishReason: STOP, MAX_TOKENS, SAFETY, RECITATION, OTHER, TOOL_CODE (或类似)
                    return {'type': 'finish', 'content': text_content, 'reason': finish_reason, 'token': token}
                
                elif text_content:
                    # 发现文本内容
                    return {'type': 'text', 'content': text_content, 'token': token}

            # 如果块既没有 finishReason 也没有有效 content parts，则忽略
            return None

        except (KeyError, IndexError, TypeError) as e:
            log('warming', f"解析 SSE 块时出错", extra={'key': self.api_key[:8]})
            # 返回错误类型，让上层决定如何处理
            return {'type': 'error', 'content': f"解析 SSE 块失败", 'reason': 'PARSE_ERROR'}
        except ValueError as e:
             # 捕获由安全检查抛出的 ValueError
             log('error', f"SSE 块包含不安全内容或错误: {e}", extra={'key': self.api_key[:8]})
             raise e # 重新抛出，让 stream_chat 处理

    # 真流式处理
    async def stream_chat(self, request: ChatCompletionRequest, contents, safety_settings, system_instruction):
        # 真流式请求处理逻辑
        extra_log = {'key': self.api_key[:8], 'request_type': 'stream', 'model': request.model}
        log('INFO', "流式请求开始", extra=extra_log)
        
        api_version, data = self._prepare_request_data(request, contents, safety_settings, system_instruction,request.model)
        model= request.model.removesuffix("-search")
        url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:streamGenerateContent?key={self.api_key}&alt=sse"
        headers = {
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, headers=headers, json=data, timeout=600) as response:
                buffer = b"" # 用于累积可能不完整的 JSON 数据
                try:
                    async for line in response.aiter_lines():
                        if not line.strip(): # 跳过空行 (SSE 消息分隔符)
                            continue
                        if line.startswith("data: "):
                            line = line[len("data: "):] # 去除 "data: " 前缀
                        
                        buffer += line.encode('utf-8')
                        try:
                            # 尝试解析整个缓冲区
                            data = json.loads(buffer.decode('utf-8'))
                            # 解析成功，清空缓冲区
                            buffer = b"" 
                            
                            # 使用辅助函数解析 SSE 块内容
                            parsed_chunk = self._parse_sse_chunk(data)
                            
                            if parsed_chunk:
                                
                                # 产生解析后的块 (字典格式)
                                yield parsed_chunk
                                
                                # 如果是结束块或错误块，提前结束循环 
                                # 当前 _parse_sse_chunk 对于 PARSE_ERROR 返回错误类型，对于 SAFETY 抛出 ValueError
                                if parsed_chunk['type'] == 'finish':
                                    break # 收到 finishReason，正常结束
                                if parsed_chunk['type'] == 'error':
                                    break # 停止处理后续块

                        except json.JSONDecodeError:
                            # JSON 不完整，继续累积到 buffer
                            continue 
                        except ValueError as ve:
                            # 捕获 _parse_sse_chunk 中因安全问题抛出的 ValueError
                            log('error', f"流处理因安全问题终止", extra=extra_log)
                            return 
                        except Exception as e:
                            error_msg = f"流式处理期间发生错误: {str(e)}"
                            extra_log_stream_error = {'key': self.api_key[:8], 'request_type': 'stream', 'model': request.model, 'status_code': 'ERROR', 'error_message': error_msg}
                            log_msg = format_log_message('ERROR', error_msg, extra=extra_log_stream_error)
                            logger.error(log_msg)
                            raise e
                except Exception as e:
                    raise e
                finally:
                    log('info', "流式请求结束")

    # 非流式处理
    def complete_chat(self, request: ChatCompletionRequest, contents, safety_settings, system_instruction):
        
        api_version, data = self._prepare_request_data(request, contents, safety_settings, system_instruction,request.model)
        model= request.model.removesuffix("-search")
        url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            return ResponseWrapper(response.json())
        except Exception as e:
            raise

    # OpenAI 格式请求转换为 gemini 格式请求
    def convert_messages(self, messages, use_system_prompt=False,model=None):
        gemini_history = []
        errors = []
        system_instruction_text = ""
        is_system_phase = use_system_prompt
        for i, message in enumerate(messages):
            role = message.role
            content = message.content
            if isinstance(content, str):
                if is_system_phase and role == 'system':
                    if system_instruction_text:
                        system_instruction_text += "\n" + content
                    else:
                        system_instruction_text = content
                else:
                    is_system_phase = False

                    if role in ['user', 'system']:
                        role_to_use = 'user'
                    elif role == 'assistant':
                        role_to_use = 'model'
                    else:
                        errors.append(f"Invalid role: {role}")
                        continue

                    if gemini_history and gemini_history[-1]['role'] == role_to_use:
                        gemini_history[-1]['parts'].append({"text": content})
                    else:
                        gemini_history.append(
                            {"role": role_to_use, "parts": [{"text": content}]})
            elif isinstance(content, list):
                parts = []
                for item in content:
                    if item.get('type') == 'text':
                        parts.append({"text": item.get('text')})
                    elif item.get('type') == 'image_url':
                        image_data = item.get('image_url', {}).get('url', '')
                        if image_data.startswith('data:image/'):
                            try:
                                mime_type, base64_data = image_data.split(';')[0].split(':')[1], image_data.split(',')[1]
                                parts.append({
                                    "inline_data": {
                                        "mime_type": mime_type,
                                        "data": base64_data
                                    }
                                })
                            except (IndexError, ValueError):
                                errors.append(
                                    f"Invalid data URI for image: {image_data}")
                        else:
                            errors.append(
                                f"Invalid image URL format for item: {item}")

                if parts:
                    if role in ['user', 'system']:
                        role_to_use = 'user'
                    elif role == 'assistant':
                        role_to_use = 'model'
                    else:
                        errors.append(f"Invalid role: {role}")
                        continue
                    if gemini_history and gemini_history[-1]['role'] == role_to_use:
                        gemini_history[-1]['parts'].extend(parts)
                    else:
                        gemini_history.append(
                            {"role": role_to_use, "parts": parts})
        if errors:
            return errors
        else:
            # 只有当search_mode为真且模型名称以-search结尾时，才添加搜索提示
            if settings.search["search_mode"] and model and model.endswith("-search"):
                gemini_history.insert(len(gemini_history)-2,{'role': 'user', 'parts': [{'text':settings.search["search_prompt"]}]})
            if settings.RANDOM_STRING:
                gemini_history.insert(1,{'role': 'user', 'parts': [{'text': generate_secure_random_string(settings.RANDOM_STRING_LENGTH)}]})
                gemini_history.insert(len(gemini_history)-1,{'role': 'user', 'parts': [{'text': generate_secure_random_string(settings.RANDOM_STRING_LENGTH)}]})
                log_msg = format_log_message('INFO', "伪装消息成功")
            return gemini_history, {"parts": [{"text": system_instruction_text}]}

    @staticmethod
    async def list_available_models(api_key) -> list:
        url = "https://generativelanguage.googleapis.com/v1beta/models?key={}".format(
            api_key)
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("models", []):
                models.append(model["name"])
                if model["name"].startswith("models/gemini-2") and settings.search["search_mode"]:
                    models.append(model["name"] + "-search")
            models.extend(GeminiClient.EXTRA_MODELS)
                
            return models
