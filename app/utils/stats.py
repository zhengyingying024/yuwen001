from datetime import datetime, timedelta
from app.utils.logging import log

def clean_expired_stats(api_call_stats):
    """清理过期统计数据的函数"""
    now = datetime.now()
    
    # 清理24小时前的数据
    for hour_key in list(api_call_stats['last_24h'].keys()):
        try:
            hour_time = datetime.strptime(hour_key, '%Y-%m-%d %H:00')
            if (now - hour_time).total_seconds() > 24 * 3600:  # 超过24小时
                del api_call_stats['last_24h'][hour_key]
        except ValueError:
            # 如果键格式不正确，直接删除
            del api_call_stats['last_24h'][hour_key]
    
    # 清理一小时前的小时统计数据
    one_hour_ago = now - timedelta(hours=1)
    for hour_key in list(api_call_stats['hourly'].keys()):
        try:
            hour_time = datetime.strptime(hour_key, '%Y-%m-%d %H:00')
            if hour_time < one_hour_ago:
                del api_call_stats['hourly'][hour_key]
        except ValueError:
            # 如果键格式不正确，直接删除
            del api_call_stats['hourly'][hour_key]
    
    # 清理一分钟前的分钟统计数据
    one_minute_ago = now - timedelta(minutes=1)
    for minute_key in list(api_call_stats['minute'].keys()):
        try:
            minute_time = datetime.strptime(minute_key, '%Y-%m-%d %H:%M')
            if minute_time < one_minute_ago:
                del api_call_stats['minute'][minute_key]
        except ValueError:
            # 如果键格式不正确，直接删除
            del api_call_stats['minute'][minute_key]

def update_api_call_stats(api_call_stats):
    """更新API调用统计的函数"""
    now = datetime.now()
    hour_key = now.strftime('%Y-%m-%d %H:00')
    minute_key = now.strftime('%Y-%m-%d %H:%M')
    
    # 检查并清理过期统计
    clean_expired_stats(api_call_stats)
    
    # 更新统计
    api_call_stats['last_24h'][hour_key] += 1
    api_call_stats['hourly'][hour_key] += 1
    api_call_stats['minute'][minute_key] += 1
    
    log('info', "API调用统计已更新: 24小时=%s, 1小时=%s, 1分钟=%s" % (
        sum(api_call_stats['last_24h'].values()), 
        sum(api_call_stats['hourly'].values()), 
        sum(api_call_stats['minute'].values())
    ))