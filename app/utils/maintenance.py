import sys
from apscheduler.schedulers.background import BackgroundScheduler
from app.utils.logging import log
from app.utils.stats import clean_expired_stats
from app.config import api_call_stats
def handle_exception(exc_type, exc_value, exc_traceback):
    """
    全局异常处理函数
    
    处理未捕获的异常，并记录到日志中
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.excepthook(exc_type, exc_value, exc_traceback)
        return
    from app.utils.error_handling import translate_error
    error_message = translate_error(str(exc_value))
    log('error', f"未捕获的异常: {error_message}", status_code=500, error_message=error_message)

def schedule_cache_cleanup(response_cache_manager, active_requests_manager):
    """
    设置定期清理缓存和活跃请求的定时任务
    
    Args:
        response_cache_manager: 响应缓存管理器实例
        active_requests_manager: 活跃请求管理器实例
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(response_cache_manager.clean_expired, 'interval', minutes=1)  # 每分钟清理过期缓存
    scheduler.add_job(active_requests_manager.clean_completed, 'interval', seconds=30)  # 每30秒清理已完成的活跃请求
    scheduler.add_job(active_requests_manager.clean_long_running, 'interval', minutes=5, args=[300])  # 每5分钟清理运行超过5分钟的任务
    scheduler.add_job(clean_expired_stats, 'interval', minutes=5,args=[api_call_stats])  # 每5分钟清理过期的统计数据
    scheduler.start()
    
    return scheduler