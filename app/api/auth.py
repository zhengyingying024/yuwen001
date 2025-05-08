from typing import Optional
from fastapi import HTTPException, Header, Query, Request
import app.config.settings as settings

# 自定义密码校验依赖函数
async def custom_verify_password(
    authorization: Optional[str] = Header(None, description="OpenAI 格式请求 Key, 格式: Bearer sk-xxxx"),
    x_goog_api_key: Optional[str] = Header(None, description="Gemini 格式请求 Key, 从请求头 x-goog-api-key 获取"),
    gemini_query_key: Optional[str] = Query(None, description="Gemini 格式请求 Key, 从查询参数 key 获取")
):
    """
    校验 API Key。
    1. 从请求中提取客户端提供的 API Key 。
    2. 根据类型，与项目配置的密钥进行比对。
    3. 如果 Key 无效、缺失或不匹配，则抛出 HTTPException。
    """
    client_provided_api_key: Optional[str] = None

    # 提取客户端提供的 Key 
    if x_goog_api_key: 
        client_provided_api_key = x_goog_api_key
    elif gemini_query_key:
        client_provided_api_key = gemini_query_key
    elif authorization and authorization.startswith("Bearer "): 
        token = authorization.split(" ", 1)[1]
        client_provided_api_key = token

    # 进行校验和比对
    if (not client_provided_api_key) or (client_provided_api_key != settings.PASSWORD) :
            raise HTTPException(
                status_code=401, detail="Unauthorized: Invalid token")


