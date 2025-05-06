import asyncio 
from datetime import datetime, timedelta
from app.utils.logging import log
from app.config.settings import stats_lock
import app.config.settings as settings
from collections import defaultdict, Counter
import time

class ApiStatsManager:
    """API调用统计管理器，优化性能的新实现"""
    
    def __init__(self):
        # 使用Counter记录API密钥和模型的调用次数
        self.api_key_counts = Counter()  # 记录每个API密钥的调用次数
        self.model_counts = Counter()    # 记录每个模型的调用次数
        self.api_model_counts = defaultdict(Counter)  # 记录每个API密钥对每个模型的调用次数
        
        # 记录token使用量
        self.api_key_tokens = Counter()  # 记录每个API密钥的token使用量
        self.model_tokens = Counter()    # 记录每个模型的token使用量
        self.api_model_tokens = defaultdict(Counter)  # 记录每个API密钥对每个模型的token使用量
        
        # 用于时间序列分析的数据结构（最近24小时，按分钟分组）
        self.time_buckets = {}  # 格式: {timestamp_minute: {"calls": count, "tokens": count}}
        
        # 保存与兼容格式相关的调用日志（最小化存储）
        self.recent_calls = []  # 仅保存最近的少量调用，用于前端展示
        self.max_recent_calls = 100  # 最大保存的最近调用记录数
        
        # 当前时间分钟桶的时间戳（分钟级别）
        self.current_minute = self._get_minute_timestamp(datetime.now())
        
        # 清理间隔（小时）
        self.cleanup_interval = 1
        self.last_cleanup = time.time()

    def _get_minute_timestamp(self, dt):
        """将时间戳转换为分钟级别的时间戳（按分钟取整）"""
        return int(dt.timestamp() // 60 * 60)
    
    async def update_stats(self, api_key, model, tokens=0):
        """更新API调用统计"""
            
        # 获取当前时间
        now = datetime.now()
        minute_ts = self._get_minute_timestamp(now)
        
        async with stats_lock:
            # 更新API密钥计数
            self.api_key_counts[api_key] += 1
            self.api_key_tokens[api_key] += tokens
            
            # 更新模型计数
            self.model_counts[model] += 1
            self.model_tokens[model] += tokens
            
            # 更新API密钥-模型组合计数
            self.api_model_counts[api_key][model] += 1
            self.api_model_tokens[api_key][model] += tokens
            
            # 更新时间序列数据
            if minute_ts not in self.time_buckets:
                self.time_buckets[minute_ts] = {"calls": 0, "tokens": 0}
            
            self.time_buckets[minute_ts]["calls"] += 1
            self.time_buckets[minute_ts]["tokens"] += tokens
            
            # 更新当前分钟
            self.current_minute = minute_ts
            
            # 添加到最近调用列表（简化版本）
            compact_call = {
                'api_key': api_key,
                'model': model,
                'timestamp': now,
                'tokens': tokens
            }
            
            self.recent_calls.append(compact_call)
            if len(self.recent_calls) > self.max_recent_calls:
                self.recent_calls.pop(0)  # 移除最旧的记录
            
            # 定期清理旧数据
            await self.maybe_cleanup(force=False)
                
            # 记录日志
            log_message = f"API调用已记录: 秘钥 '{api_key[:8]}', 模型 '{model}', 令牌: {tokens if tokens is not None else 0}"
            log('info', log_message)
            
    async def maybe_cleanup(self, force=False):
        """根据需要清理旧数据"""
        now = time.time()
        if force or (now - self.last_cleanup > self.cleanup_interval * 3600):
            await self.cleanup()
            self.last_cleanup = now
    
    async def cleanup(self):
        """清理超过24小时的时间桶数据"""
        now = datetime.now()
        day_ago_ts = self._get_minute_timestamp(now - timedelta(days=1))
        
        # 清理旧的时间桶
        async with stats_lock:
            self.time_buckets = {ts: data for ts, data in self.time_buckets.items() 
                               if ts >= day_ago_ts}
    
    async def get_api_key_usage(self, api_key, model=None):
        """获取API密钥的使用统计"""
        async with stats_lock:
            # 可能触发清理
            await self.maybe_cleanup(force=False)
            
            if model:
                # 返回特定API密钥和模型的调用次数
                return self.api_model_counts[api_key][model]
            else:
                # 返回特定API密钥的总调用次数
                return self.api_key_counts[api_key]
    
    def get_calls_last_24h(self):
        """获取过去24小时的总调用次数"""
        return sum(self.api_key_counts.values())
    
    def get_calls_last_hour(self, now=None):
        """获取过去一小时的总调用次数"""
        if now is None:
            now = datetime.now()
        
        hour_ago_ts = self._get_minute_timestamp(now - timedelta(hours=1))
        return sum(data["calls"] for ts, data in self.time_buckets.items() 
                  if ts >= hour_ago_ts)
    
    def get_calls_last_minute(self, now=None):
        """获取过去一分钟的总调用次数"""
        if now is None:
            now = datetime.now()
        
        minute_ago_ts = self._get_minute_timestamp(now - timedelta(minutes=1))
        return sum(data["calls"] for ts, data in self.time_buckets.items() 
                  if ts >= minute_ago_ts)
    
    def get_time_series_data(self, minutes=30, now=None):
        """获取过去N分钟的时间序列数据（调用次数和token使用量）"""
        if now is None:
            now = datetime.now()
            
        calls_series = []
        tokens_series = []
        
        for i in range(minutes, -1, -1):
            minute_dt = now - timedelta(minutes=i)
            minute_ts = self._get_minute_timestamp(minute_dt)
            
            # 获取这个分钟的数据
            bucket = self.time_buckets.get(minute_ts, {"calls": 0, "tokens": 0})
            
            calls_series.append({
                'time': minute_dt.strftime('%H:%M'),
                'value': bucket["calls"]
            })
            
            tokens_series.append({
                'time': minute_dt.strftime('%H:%M'),
                'value': bucket["tokens"]
            })
        
        return calls_series, tokens_series
    
    def get_api_key_stats(self, api_keys):
        """获取API密钥的详细统计信息，用于仪表板显示"""
        stats = []
        
        for api_key in api_keys:
            # 获取API密钥前8位作为标识
            api_key_id = api_key[:8]
            
            # 计算24小时内的调用次数和token数
            calls_24h = self.api_key_counts[api_key]
            total_tokens = self.api_key_tokens[api_key]
            
            # 获取按模型分类的统计
            model_stats = {}
            for model, count in self.api_model_counts[api_key].items():
                tokens = self.api_model_tokens[api_key][model]
                model_stats[model] = {
                    'calls': count,
                    'tokens': tokens
                }
            
            # 计算使用百分比
            usage_percent = (calls_24h / settings.API_KEY_DAILY_LIMIT) * 100 if settings.API_KEY_DAILY_LIMIT > 0 else 0
            
            # 添加到结果列表
            stats.append({
                'api_key': api_key_id,
                'calls_24h': calls_24h,
                'total_tokens': total_tokens,
                'limit': settings.API_KEY_DAILY_LIMIT,
                'usage_percent': round(usage_percent, 2),
                'model_stats': model_stats
            })
        
        # 按使用百分比降序排序
        stats.sort(key=lambda x: x['usage_percent'], reverse=True)
        return stats
    
    async def reset(self):
        """重置所有统计数据"""
        async with stats_lock:
            self.api_key_counts.clear()
            self.model_counts.clear()
            self.api_model_counts.clear()
            self.api_key_tokens.clear()
            self.model_tokens.clear()
            self.api_model_tokens.clear()
            self.time_buckets.clear()
            self.recent_calls.clear()
            self.current_minute = self._get_minute_timestamp(datetime.now())
            self.last_cleanup = time.time()

# 创建全局单例实例
api_stats_manager = ApiStatsManager()

# 兼容现有代码的函数

def clean_expired_stats(api_call_stats):
    """清理过期统计数据的函数 (兼容旧接口)"""
    asyncio.create_task(api_stats_manager.cleanup())

async def update_api_call_stats(api_call_stats, endpoint=None, model=None, token=None): 
    """更新API调用统计的函数 (兼容旧接口)"""
    if endpoint and model:
        await api_stats_manager.update_stats(endpoint, model, token if token is not None else 0)

async def get_api_key_usage(api_call_stats, api_key, model=None):
    """获取API密钥的调用次数 (兼容旧接口)"""
    return await api_stats_manager.get_api_key_usage(api_key, model) 