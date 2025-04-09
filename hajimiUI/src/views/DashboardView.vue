<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import StatusSection from '../components/dashboard/StatusSection.vue'
import ConfigSection from '../components/dashboard/ConfigSection.vue'
import LogSection from '../components/dashboard/LogSection.vue'
import { useDashboardStore } from '../stores/dashboard'

const dashboardStore = useDashboardStore()
const refreshInterval = ref(null)

// 计算属性：夜间模式状态
const isDarkMode = computed(() => dashboardStore.isDarkMode)

// 页面加载时获取数据并启动自动刷新
onMounted(() => {
  fetchDashboardData()
  startAutoRefresh()
})

// 组件卸载时停止自动刷新
onUnmounted(() => {
  stopAutoRefresh()
})

// 开始自动刷新
function startAutoRefresh() {
  if (!refreshInterval.value) {
    refreshInterval.value = setInterval(fetchDashboardData, 1000) // 1秒刷新一次
    console.log('自动刷新已启动')
  }
}

// 停止自动刷新
function stopAutoRefresh() {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
    refreshInterval.value = null
    console.log('自动刷新已停止')
  }
}

// 获取仪表盘数据
async function fetchDashboardData() {
  await dashboardStore.fetchDashboardData()
}

// 手动刷新
function handleRefresh() {
  fetchDashboardData()
}

// 切换夜间模式
function toggleDarkMode() {
  dashboardStore.toggleDarkMode()
}
</script>

<template>
  <div class="dashboard">
    <div class="header-container">
      <h1>🤖 Gemini API 代理服务</h1>
      <div class="theme-toggle">
        <label class="switch">
          <input type="checkbox" :checked="isDarkMode" @change="toggleDarkMode">
          <span class="slider round"></span>
        </label>
        <span class="toggle-label">{{ isDarkMode ? '🌙' : '☀️' }}</span>
      </div>
    </div>
    
    <!-- 运行状态部分 -->
    <StatusSection />
    
    <!-- 环境配置部分 -->
    <ConfigSection />
    
    <!-- 系统日志部分 -->
    <LogSection />
    
    <button class="refresh-button" @click="handleRefresh">刷新数据</button>
  </div>
</template>

<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.6;
  background-color: var(--color-background);
  color: var(--color-text);
  margin: 0;
  padding: 0;
  transition: background-color 0.3s, color 0.3s;
}

.dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

h1 {
  color: var(--color-heading);
  margin: 0;
  font-size: 1.8rem;
}

/* 主题切换开关 */
.theme-toggle {
  display: flex;
  align-items: center;
}

.toggle-label {
  margin-left: 8px;
  font-size: 1.2rem;
}

/* 开关样式 */
.switch {
  position: relative;
  display: inline-block;
  width: 60px;
  height: 30px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--toggle-bg);
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 22px;
  width: 22px;
  left: 4px;
  bottom: 4px;
  background-color: white;
  transition: .4s;
}

input:checked + .slider {
  background-color: var(--toggle-active);
}

input:focus + .slider {
  box-shadow: 0 0 1px var(--toggle-active);
}

input:checked + .slider:before {
  transform: translateX(30px);
}

.slider.round {
  border-radius: 34px;
}

.slider.round:before {
  border-radius: 50%;
}

/* 移动端优化 - 减小整体边距 */
@media (max-width: 768px) {
  .dashboard {
    padding: 10px 8px;
  }
  
  .header-container {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
  }
  
  h1 {
    font-size: 1.4rem;
    text-align: left;
    margin-right: 10px;
  }
}

@media (max-width: 480px) {
  .dashboard {
    padding: 6px 4px;
  }
  
  h1 {
    font-size: 1.2rem;
  }
  
  .switch {
    width: 50px;
    height: 26px;
  }
  
  .slider:before {
    height: 18px;
    width: 18px;
  }
  
  input:checked + .slider:before {
    transform: translateX(24px);
  }
  
  .toggle-label {
    margin-left: 5px;
    font-size: 1rem;
  }
}

.refresh-button {
  display: block;
  margin: 20px auto;
  padding: 10px 20px;
  background-color: var(--button-primary);
  color: var(--button-text);
  border: none;
  border-radius: 4px;
  font-size: 16px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.refresh-button:hover {
  background-color: var(--button-primary-hover);
}

/* 全局响应式样式 - 保持三栏布局但优化显示 */
@media (max-width: 768px) {
  /* 覆盖所有组件中的卡片样式 */
  :deep(.info-box) {
    padding: 10px 6px;
    margin-bottom: 10px;
    border-radius: 6px;
    background-color: var(--card-background);
    border: 1px solid var(--card-border);
  }
  
  :deep(.section-title) {
    font-size: 1.1rem;
    margin-bottom: 10px;
    padding-bottom: 6px;
    color: var(--color-heading);
    border-bottom: 1px solid var(--color-border);
  }
  
  :deep(.stats-grid) {
    gap: 5px;
    margin-top: 10px;
    margin-bottom: 15px;
  }
  
  .refresh-button {
    margin: 15px auto;
    padding: 8px 16px;
    font-size: 14px;
  }
}

/* 小屏幕手机适配 */
@media (max-width: 480px) {
  :deep(.info-box) {
    padding: 8px 4px;
    margin-bottom: 6px;
    border-radius: 5px;
  }
  
  :deep(.section-title) {
    font-size: 1rem;
    margin-bottom: 8px;
    padding-bottom: 4px;
  }
  
  :deep(.stats-grid) {
    gap: 4px;
    margin-top: 8px;
    margin-bottom: 10px;
  }
  
  .refresh-button {
    margin: 10px auto;
    padding: 6px 12px;
    font-size: 13px;
  }
}
</style>