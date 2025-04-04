from fastapi import APIRouter
from datetime import datetime, timedelta
from app.utils import (
    log_manager,
    ResponseCacheManager,
    ActiveRequestsManager,
    clean_expired_stats
)
from app.config.settings import (
    api_call_stats,
    client_request_history,
    api_call_stats
)
from app.services import GeminiClient

# 创建路由器
dashboard_router = APIRouter(prefix="/api", tags=["dashboard"])

# 全局变量引用，将在init_dashboard_router中设置
key_manager = None
response_cache_manager = None
active_requests_manager = None

def init_dashboard_router(
    key_mgr,
    cache_mgr,
    active_req_mgr
):
    """初始化仪表盘路由器"""
    global key_manager, response_cache_manager, active_requests_manager
    key_manager = key_mgr
    response_cache_manager = cache_mgr
    active_requests_manager = active_req_mgr
    return dashboard_router

@dashboard_router.get("/dashboard-data")
async def get_dashboard_data():
    """获取仪表盘数据的API端点，用于动态刷新"""
    # 先清理过期数据，确保统计数据是最新的
    clean_expired_stats(api_call_stats)
    response_cache_manager.clean_expired()  # 使用管理器清理缓存
    active_requests_manager.clean_completed()  # 使用管理器清理活跃请求
    
    # 获取当前统计数据
    now = datetime.now()
    
    # 计算过去24小时的调用总数
    last_24h_calls = sum(api_call_stats['last_24h']['total']['total'].values())
    
    # 计算过去一小时内的调用总数
    one_hour_ago = now - timedelta(hours=1)
    hourly_calls = 0
    for hour_key, count in api_call_stats['hourly']['total'].items():
        try:
            hour_time = datetime.strptime(hour_key, '%Y-%m-%d %H:00')
            if hour_time >= one_hour_ago:
                hourly_calls += count
        except ValueError:
            continue
    
    # 计算过去一分钟内的调用总数
    one_minute_ago = now - timedelta(minutes=1)
    minute_calls = 0
    for minute_key, count in api_call_stats['minute']['total'].items():
        try:
            minute_time = datetime.strptime(minute_key, '%Y-%m-%d %H:%M')
            if minute_time >= one_minute_ago:
                minute_calls += count
        except ValueError:
            continue
    
    # 获取最近的日志
    recent_logs = log_manager.get_recent_logs(50)  # 获取最近50条日志
    
    # 返回JSON格式的数据
    return {
        "key_count": len(key_manager.api_keys),
        "model_count": len(GeminiClient.AVAILABLE_MODELS),
        "retry_count": len(key_manager.api_keys),
        "last_24h_calls": last_24h_calls,
        "hourly_calls": hourly_calls,
        "minute_calls": minute_calls,
        "current_time": datetime.now().strftime('%H:%M:%S'),
        "logs": recent_logs
    }