<script setup>
import { useDashboardStore } from '../../stores/dashboard'
import { ref } from 'vue'

const dashboardStore = useDashboardStore()
const isExpanded = ref(true)

// 配置项解释
const configExplanations = {
  maxRequestsPerMinute: '限制每个IP每分钟可以发送的最大请求数量，防止API被滥用',
  maxRequestsPerDayPerIp: '限制每个IP每天可以发送的最大请求数量，防止API被滥用',
  currentTime: '当前服务器时间，用于同步和调试',
  fakeStreaming: '是否启用假流式响应，模拟流式返回效果',
  fakeStreamingInterval: '假流式响应的间隔时间（秒），控制返回速度',
  randomString: '是否启用随机字符串生成，用于伪装请求',
  randomStringLength: '随机字符串的长度，用于伪装请求',
  concurrentRequests: '默认并发请求数量，控制同时处理的请求数',
  increaseConcurrentOnFailure: '请求失败时增加的并发数，提高成功率',
  maxConcurrentRequests: '最大并发请求数量，防止系统过载',
  localVersion: '当前系统版本号',
  remoteVersion: '远程仓库最新版本号',
  hasUpdate: '是否有可用更新'
}

// 显示解释的工具提示
const showTooltip = ref(false)
const tooltipText = ref('')
const tooltipPosition = ref({ x: 0, y: 0 })

function showExplanation(text, event) {
  tooltipText.value = text
  tooltipPosition.value = {
    x: event.clientX,
    y: event.clientY
  }
  showTooltip.value = true
}

function hideTooltip() {
  showTooltip.value = false
}

// 获取折叠图标类
const getFoldIconClass = (isVisible) => {
  return isVisible ? 'fold-icon rotated' : 'fold-icon'
}
</script>

<template>
  <div class="info-box">
    <h3 class="section-title fold-header" @click="isExpanded = !isExpanded">
      ⚙️ 环境配置
      <span :class="getFoldIconClass(isExpanded)">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </span>
    </h3>
    
    <!-- 默认显示的一行三栏 -->
    <div class="stats-grid" v-if="!isExpanded">
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.maxRequestsPerMinute }}</div>
        <div class="stat-label">每分钟请求限制</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.concurrentRequests }}</div>
        <div class="stat-label">并发请求数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ dashboardStore.config.currentTime }}</div>
        <div class="stat-label">当前服务器时间</div>
      </div>
    </div>
    
    <!-- 展开后显示的所有配置项 -->
    <transition name="fold">
      <div v-if="isExpanded" class="fold-content">
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
            <div class="stat-value">{{ dashboardStore.config.searchMode ? "启用" : "禁用" }}</div>
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
            <div class="stat-value">{{ dashboardStore.config.randomStringLength }}字符</div>
            <div class="stat-label">伪装信息长度</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ dashboardStore.config.concurrentRequests }}</div>
            <div class="stat-label">默认并发请求数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ dashboardStore.config.increaseConcurrentOnFailure }}</div>
            <div class="stat-label">失败时增加并发数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ dashboardStore.config.maxConcurrentRequests }}</div>
            <div class="stat-label">最大并发请求数</div>
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

        <!-- 项目地址 -->
        <div class="project-link-container">
          <a href="https://github.com/wyeeeee/hajimi" target="_blank" rel="noopener noreferrer" class="project-link">
            <span class="github-icon">🌸</span>
            <span class="project-text">项目地址：github.com/wyeeeee/hajimi</span>
            <span class="github-icon">🌸</span>
          </a>
        </div>
      </div>
    </transition>
    
    <!-- 工具提示 -->
    <div class="tooltip" v-if="showTooltip" :style="{ left: tooltipPosition.x + 'px', top: tooltipPosition.y + 'px' }" @mouseleave="hideTooltip">
      {{ tooltipText }}
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
  position: relative;
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
  position: relative;
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

/* 工具提示样式 */
.tooltip {
  position: fixed;
  background-color: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  max-width: 250px;
  z-index: 1000;
  pointer-events: none;
  transform: translate(-50%, -100%);
  margin-top: -10px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
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
  
  .tooltip {
    max-width: 200px;
    font-size: 10px;
  }
}

/* 版本更新状态样式 */
.update-needed {
  color: #dc3545 !important; /* 红色 - 需要更新 */
}

.up-to-date {
  color: #28a745 !important; /* 绿色 - 已是最新 */
}

/* 折叠动画和UI优化 */
.fold-header {
  cursor: pointer;
  user-select: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background-color 0.2s;
  border-radius: 6px;
  padding: 5px 8px;
}

.fold-header:hover {
  background-color: var(--color-background-mute);
}

.fold-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.3s ease;
}

.fold-icon.rotated {
  transform: rotate(180deg);
}

.fold-content {
  overflow: hidden;
}

/* 折叠动画 */
.fold-enter-active,
.fold-leave-active {
  transition: all 0.3s ease;
  max-height: 1000px;
  opacity: 1;
  overflow: hidden;
}

.fold-enter-from,
.fold-leave-to {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
}

/* 项目链接样式 */
.project-link-container {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 12px;
  margin-top: 15px;
  transition: all 0.3s ease;
}

.project-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--button-primary);
  text-decoration: none;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 20px;
  background-color: var(--stats-item-bg);
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.project-link:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
  background-color: var(--color-background-mute);
}

.github-icon {
  font-size: 16px;
  opacity: 0.8;
  transition: all 0.3s ease;
}

.project-link:hover .github-icon {
  opacity: 1;
  transform: scale(1.1);
}

.project-text {
  font-weight: 500;
}

/* 移动端优化 */
@media (max-width: 768px) {
  .project-link {
    font-size: 12px;
    padding: 6px 12px;
  }
  
  .github-icon {
    font-size: 14px;
  }
}

@media (max-width: 480px) {
  .project-link {
    font-size: 11px;
    padding: 4px 10px;
  }
  
  .github-icon {
    font-size: 12px;
  }
}
</style>