import requests
import json
import os
import asyncio
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

@dataclass
class GeneratedText:
    text: str
    finish_reason: Optional[str] = None


class GeminiResponseWrapper:
    def __init__(self, data: Dict[Any, Any]):  
        self._data = data
        self._text = self._extract_text()
        self._finish_reason = self._extract_finish_reason()
        self._prompt_token_count = self._extract_prompt_token_count()
        self._candidates_token_count = self._extract_candidates_token_count()
        self._total_token_count = self._extract_total_token_count()
        self._thoughts = self._extract_thoughts()
        self._function_call = self._extract_function_call()
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
                    tex += part['text']
            return text
        except (KeyError, IndexError):
            return ""

    # 提取 functionCall 
    def _extract_function_call(self) -> Optional[Dict[str, Any]]:
        try:
            # 检查 candidates[0].content.parts 是否存在 functionCall
            parts = self._data.get('candidates', [{}])[0].get('content', {}).get('parts', [])
            for part in parts:
                if 'functionCall' in part:
                    return part['functionCall']
            return None
        except (KeyError, IndexError, TypeError):
            # 如果结构不符合预期或不存在 functionCall，返回 None
            return None

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

    # 新增：function_call 属性
    @property
    def function_call(self) -> Optional[Dict[str, Any]]:
        return self._function_call


class GeminiClient:

    AVAILABLE_MODELS = []
    EXTRA_MODELS = os.environ.get("EXTRA_MODELS", "").split(",")

    def __init__(self, api_key: str):
        self.api_key = api_key

    # 请求参数处理
    def _prepare_request_data(self, request, contents, safety_settings, system_instruction,model):
        
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
        generationConfig = {k: v for k, v in config_params.items() if v is not None}
        
        api_version = "v1alpha" if "think" in request.model else "v1beta"
        
        data = {
            "contents": contents,
            "generationConfig": generationConfig,
            "safetySettings": safety_settings,
        }
        
        if settings.search["search_mode"] and model.endswith("-search"):
            log('INFO', "开启联网搜索模式", extra={'key': self.api_key[:8], 'model':request.model})
            data.setdefault("tools", []).append({"google_search": {}})
        
        if system_instruction:
            data["system_instruction"] = system_instruction
        
        return api_version, data
    

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
                            line = line[len("data: "):].strip() # 去除 "data: " 前缀
                        
                        # 检查是否是结束标志，如果是，结束循环
                        if line == "[DONE]":
                            break 
                        
                        buffer += line.encode('utf-8')
                        try:
                            # 尝试解析整个缓冲区
                            data = json.loads(buffer.decode('utf-8'))
                            # 解析成功，清空缓冲区
                            buffer = b"" 
                            
                            yield GeminiResponseWrapper(data)

                        except json.JSONDecodeError:
                            # JSON 不完整，继续累积到 buffer
                            continue 
                        except Exception as e:
                            log('ERROR', f"流式处理期间发生错误", 
                                extra={'key': self.api_key[:8], 'request_type': 'stream', 'model': request.model})
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
            
            return GeminiResponseWrapper(response.json())
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
