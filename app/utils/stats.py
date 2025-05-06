import asyncio 
from datetime import datetime, timedelta
from app.utils.logging import log
from app.config.settings import stats_lock
import app.config.settings as settings
from collections import defaultdict, Counter
import time
import threading
import queue
from functools import wraps

class ApiStatsManager:
    """
    API调用统计管理器，优化性能的新实现
    
    性能优化：
    1. 后台处理 - 可选使用后台线程处理统计更新
    2. 细粒度锁 - 避免全局锁竞争
    3. 批量处理 - 合并短时间内的统计更新
    4. 高效清理 - 改进过期数据清理机制
    """
    
    def __init__(self, use_background_thread=True, batch_interval=1.0):
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
        
        # 细粒度锁，避免全局锁竞争
        self.counters_lock = asyncio.Lock()  # 保护计数器
        self.time_lock = asyncio.Lock()      # 保护时间序列数据
        self.calls_lock = asyncio.Lock()     # 保护最近调用记录
        
        # 后台处理选项
        self.use_background = use_background_thread
        self.batch_interval = batch_interval  # 批处理间隔（秒）
        
        # 设置后台处理
        if self.use_background:
            self.stats_queue = queue.Queue()
            self.worker_thread = threading.Thread(target=self._background_worker, daemon=True)
            self.worker_thread.start()
            self.last_batch_time = time.time()
            self.batch_buffer = []
            
    def _background_worker(self):
        """处理后台统计更新的工作线程"""
        while True:
            try:
                # 从队列获取统计更新
                update_data = self.stats_queue.get(timeout=0.5)
                
                if update_data is None:  # 终止信号
                    break
                    
                # 应用统计更新（在后台线程中）
                api_key, model, tokens, timestamp = update_data
                self._apply_stats_update(api_key, model, tokens, timestamp)
                
                # 标记任务完成
                self.stats_queue.task_done()
                
                # 适当时执行清理操作
                now = time.time()
                if now - self.last_cleanup > self.cleanup_interval * 3600:
                    self._sync_cleanup()
                    self.last_cleanup = now
                    
            except queue.Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                # 记录错误但不中断工作线程
                log('error', f"统计后台处理错误: {str(e)}")
                
    def _sync_cleanup(self):
        """后台线程中使用的同步清理方法"""
        now = datetime.now()
        day_ago_ts = self._get_minute_timestamp(now - timedelta(days=1))
        
        # 清理旧的时间桶（不需要锁，因为在单独的线程中）
        self.time_buckets = {ts: data for ts, data in self.time_buckets.items() 
                           if ts >= day_ago_ts}
                
    def _apply_stats_update(self, api_key, model, tokens, timestamp):
        """直接应用统计更新（用于后台处理）"""
        # 计算时间戳分钟值
        minute_ts = self._get_minute_timestamp(timestamp)
        
        # 更新API密钥和模型计数
        self.api_key_counts[api_key] += 1
        self.api_key_tokens[api_key] += tokens
        self.model_counts[model] += 1
        self.model_tokens[model] += tokens
        self.api_model_counts[api_key][model] += 1
        self.api_model_tokens[api_key][model] += tokens
        
        # 更新时间序列数据
        if minute_ts not in self.time_buckets:
            self.time_buckets[minute_ts] = {"calls": 0, "tokens": 0}
        
        self.time_buckets[minute_ts]["calls"] += 1
        self.time_buckets[minute_ts]["tokens"] += tokens
        
        # 更新当前分钟
        if minute_ts > self.current_minute:
            self.current_minute = minute_ts
            
        # 添加到最近调用列表
        compact_call = {
            'api_key': api_key,
            'model': model,
            'timestamp': timestamp,
            'tokens': tokens
        }
        
        self.recent_calls.append(compact_call)
        if len(self.recent_calls) > self.max_recent_calls:
            self.recent_calls.pop(0)  # 移除最旧的记录

    def _get_minute_timestamp(self, dt):
        """将时间戳转换为分钟级别的时间戳（按分钟取整）"""
        return int(dt.timestamp() // 60 * 60)
    
    async def update_stats(self, api_key, model, tokens=0):
        """更新API调用统计"""
        if settings.PUBLIC_MODE:
            return
            
        # 获取当前时间
        now = datetime.now()
        
        # 如果启用了后台处理
        if self.use_background:
            # 将更新添加到队列
            self.stats_queue.put((api_key, model, tokens, now))
            
            # 记录日志（这部分仍在主线程，提供即时反馈）
            log_message = f"API调用已记录: 秘钥 '{api_key[:8]}', 模型 '{model}', 令牌: {tokens if tokens is not None else 0}"
            log('info', log_message)
            return
            
        # 直接处理模式（未使用后台线程）
        minute_ts = self._get_minute_timestamp(now)
        
        # 使用细粒度锁分别更新不同部分的数据
        
        # 1. 更新计数器
        async with self.counters_lock:
            self.api_key_counts[api_key] += 1
            self.api_key_tokens[api_key] += tokens
            self.model_counts[model] += 1
            self.model_tokens[model] += tokens
            self.api_model_counts[api_key][model] += 1
            self.api_model_tokens[api_key][model] += tokens
        
        # 2. 更新时间序列数据
        async with self.time_lock:
            if minute_ts not in self.time_buckets:
                self.time_buckets[minute_ts] = {"calls": 0, "tokens": 0}
            
            self.time_buckets[minute_ts]["calls"] += 1
            self.time_buckets[minute_ts]["tokens"] += tokens
            
            # 更新当前分钟
            if minute_ts > self.current_minute:
                self.current_minute = minute_ts
        
        # 3. 更新最近调用列表
        async with self.calls_lock:
            compact_call = {
                'api_key': api_key,
                'model': model,
                'timestamp': now,
                'tokens': tokens
            }
            
            self.recent_calls.append(compact_call)
            if len(self.recent_calls) > self.max_recent_calls:
                self.recent_calls.pop(0)  # 移除最旧的记录
        
        # 4. 定期清理旧数据（不加锁，因为清理函数中有锁）
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
        # 如果使用后台处理，则不需要主线程中执行清理
        if self.use_background:
            return
            
        now = datetime.now()
        day_ago_ts = self._get_minute_timestamp(now - timedelta(days=1))
        
        # 清理旧的时间桶
        async with self.time_lock:
            # 使用字典推导式过滤，而不是创建新字典
            old_keys = [ts for ts in self.time_buckets if ts < day_ago_ts]
            for key in old_keys:
                del self.time_buckets[key]
    
    async def get_api_key_usage(self, api_key, model=None):
        """获取API密钥的使用统计"""
        # 如果使用了后台处理，结果可能不是完全实时的
        async with self.counters_lock:
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
        
        # 提前计算所有需要的时间戳
        minute_timestamps = []
        for i in range(minutes, -1, -1):
            minute_dt = now - timedelta(minutes=i)
            minute_ts = self._get_minute_timestamp(minute_dt)
            minute_timestamps.append((minute_dt, minute_ts))
        
        # 一次性获取所有数据，减少锁定时间
        buckets_copy = {}
        
        # 非阻塞方式读取时间桶数据
        # 这里可能会出现不一致的数据，但对于仪表板展示是可接受的
        buckets_copy = self.time_buckets.copy()
            
        # 生成时间序列
        for minute_dt, minute_ts in minute_timestamps:
            # 获取这个分钟的数据
            bucket = buckets_copy.get(minute_ts, {"calls": 0, "tokens": 0})
            
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
        
        # 创建计数器数据的快照，避免长时间锁定
        # 这可能导致数据稍微过时，但对仪表板显示是可接受的
        snapshot_key_counts = self.api_key_counts.copy()
        snapshot_key_tokens = self.api_key_tokens.copy()
        snapshot_model_counts = {}
        snapshot_model_tokens = {}
        
        # 为了减少锁争用，我们采用非阻塞方式获取数据
        for api_key in api_keys:
            if api_key in self.api_model_counts:
                snapshot_model_counts[api_key] = self.api_model_counts[api_key].copy()
                
            if api_key in self.api_model_tokens:
                snapshot_model_tokens[api_key] = self.api_model_tokens[api_key].copy()
        
        # 处理每个API密钥
        for api_key in api_keys:
            # 获取API密钥前8位作为标识
            api_key_id = api_key[:8]
            
            # 计算24小时内的调用次数和token数
            calls_24h = snapshot_key_counts.get(api_key, 0)
            total_tokens = snapshot_key_tokens.get(api_key, 0)
            
            # 获取按模型分类的统计
            model_stats = {}
            
            # 获取模型统计
            if api_key in snapshot_model_counts:
                for model, count in snapshot_model_counts[api_key].items():
                    tokens = snapshot_model_tokens.get(api_key, {}).get(model, 0)
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
        # 同时获取所有锁以确保一致性重置
        # 使用上下文管理器同时管理多个锁，避免死锁
        if self.use_background:
            # 清空队列
            while not self.stats_queue.empty():
                try:
                    self.stats_queue.get_nowait()
                    self.stats_queue.task_done()
                except queue.Empty:
                    break
        
        # 同时获取所有锁
        async with self.counters_lock, self.time_lock, self.calls_lock:
            # 重置所有数据结构
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

# 创建全局单例实例 - 默认启用后台处理
api_stats_manager = ApiStatsManager(use_background_thread=True)

# 兼容现有代码的函数

def clean_expired_stats(api_call_stats):
    """清理过期统计数据的函数 (兼容旧接口)"""
    asyncio.create_task(api_stats_manager.cleanup())

async def update_api_call_stats(api_call_stats, endpoint=None, model=None, token=None): 
    """更新API调用统计的函数 (兼容旧接口)"""
    if settings.PUBLIC_MODE:
        return
        
    if endpoint and model:
        await api_stats_manager.update_stats(endpoint, model, token if token is not None else 0)
    else:
        log('warning', "API调用记录不完整: 缺少秘钥或模型信息")

async def get_api_key_usage(api_call_stats, api_key, model=None):
    """获取API密钥的调用次数 (兼容旧接口)"""
    return await api_stats_manager.get_api_key_usage(api_key, model) 