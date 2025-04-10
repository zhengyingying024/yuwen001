<script setup>
import { useDashboardStore } from '../../stores/dashboard'

const dashboardStore = useDashboardStore()
</script>

<template>
  <div class="info-box">
    <h2 class="section-title">⚙️ 环境配置</h2>
    
    <!-- 基本配置 -->
    <h3 class="section-title">基本配置</h3>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.maxRequestsPerMinute }}</div>
        <div class="stat-label">每分钟请求限制</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.maxRequestsPerDayPerIp }}</div>
        <div class="stat-label">每IP每日请求限制</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.currentTime }}</div>
        <div class="stat-label">当前服务器时间</div>
      </div>
    </div>
    
    <!-- 功能配置 -->
    <h3 class="section-title">功能配置</h3>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.fakeStreaming ? "启用" : "禁用" }}</div>
        <div class="stat-label">联网搜索</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.fakeStreaming ? "启用" : "禁用" }}</div>
        <div class="stat-label">假流式响应</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.fakeStreamingInterval }}秒</div>
        <div class="stat-label">假流式间隔</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.randomString ? "启用" : "禁用" }}</div>
        <div class="stat-label">伪装信息</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.fakeStreamingInterval }}字符</div>
        <div class="stat-label">伪装信息长度</div>
      </div>
    </div>
    
    <!-- 版本信息 -->
    <h3 class="section-title">版本信息</h3>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.localVersion }}</div>
        <div class="stat-label">当前版本</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.remoteVersion }}</div>
        <div class="stat-label">最新版本</div>
      </div>
      <div class="stat-card">
        <div 
          class="stat-value" 
          :class="dashboardStore.config.hasUpdate ? 'update-needed' : 'up-to-date'"
        >
          {{ dashboardStore.config.hasUpdate ? "需要更新" : "已是最新" }}
        </div>
        <div class="stat-label">更新状态</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.info-box {
  background-color: var(--card-background);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  transition: background-color 0.3s, border-color 0.3s, box-shadow 0.3s;
}

/* 移动端优化 - 减小外边距 */
@media (max-width: 768px) {
  .info-box {
    margin-bottom: 12px;
  }
}

@media (max-width: 480px) {
  .info-box {
    margin-bottom: 8px;
  }
}

.section-title {
  color: var(--color-heading);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 10px;
  margin-bottom: 20px;
  transition: color 0.3s, border-color 0.3s;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 15px;
  margin-top: 15px;
  margin-bottom: 20px;
}

/* 移动端优化 - 保持三栏但减小间距 */
@media (max-width: 768px) {
  .stats-grid {
    gap: 6px;
  }
}

.stat-card {
  background-color: var(--stats-item-bg);
  padding: 15px;
  border-radius: 8px;
  text-align: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  transition: transform 0.2s, background-color 0.3s, box-shadow 0.3s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--button-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.3s;
}

.stat-label {
  font-size: 14px;
  color: var(--color-text);
  margin-top: 5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.3s;
}

/* 移动端优化 - 更紧凑的卡片 */
@media (max-width: 768px) {
  .stat-card {
    padding: 8px 5px;
  }
  
  .stat-value {
    font-size: 16px;
  }
  
  .stat-label {
    font-size: 11px;
    margin-top: 3px;
  }
}

/* 小屏幕手机进一步优化 */
@media (max-width: 480px) {
  .stat-card {
    padding: 6px 3px;
  }
  
  .stat-value {
    font-size: 14px;
  }
  
  .stat-label {
    font-size: 10px;
    margin-top: 2px;
  }
}

/* 版本更新状态样式 */
.update-needed {
  color: #dc3545 !important; /* 红色 - 需要更新 */
}

.up-to-date {
  color: #28a745 !important; /* 绿色 - 已是最新 */
}
</style>