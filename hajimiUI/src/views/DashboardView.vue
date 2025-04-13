<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import StatusSection from '../components/dashboard/StatusSection.vue'
import ConfigSection from '../components/dashboard/ConfigSection.vue'
import LogSection from '../components/dashboard/LogSection.vue'
import { useDashboardStore } from '../stores/dashboard'

const dashboardStore = useDashboardStore()
const refreshInterval = ref(null)
const isPageLoaded = ref(false)
const animationStep = ref(0)
const animationCompleted = ref(false)

// 计算属性：夜间模式状态
const isDarkMode = computed(() => dashboardStore.isDarkMode)

// 页面加载时获取数据并启动自动刷新
onMounted(() => {
  fetchDashboardData()
  startAutoRefresh()
  
  // 添加开屏动画效果
  setTimeout(() => {
    isPageLoaded.value = true
    
    // 逐步触发动画
    const animateStep = () => {
      if (animationStep.value < 10) {
        animationStep.value++
        setTimeout(animateStep, 100)
      } else {
        // 动画完成后标记
        animationCompleted.value = true
      }
    }
    
    setTimeout(animateStep, 50)
  }, 50)
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
  <div class="dashboard" :class="{ 'page-loaded': isPageLoaded }">
    <div class="header-container" :class="{ 'animate-in': animationStep >= 1 || animationCompleted }">
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
    <StatusSection class="section-animate" :class="{ 'animate-in': animationStep >= 2 || animationCompleted }" />
    
    <!-- 环境配置部分 -->
    <ConfigSection class="section-animate" :class="{ 'animate-in': animationStep >= 3 || animationCompleted }" />
    
    <!-- 系统日志部分 -->
    <LogSection class="section-animate" :class="{ 'animate-in': animationStep >= 4 || animationCompleted }" />
    
    <button class="refresh-button" :class="{ 'animate-in': animationStep >= 5 || animationCompleted }" @click="handleRefresh">刷新数据</button>
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
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94), transform 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.dashboard.page-loaded {
  opacity: 1;
  transform: translateY(0);
}

.header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  opacity: 0;
  transform: translateY(20px) scale(0.95);
  transition: opacity 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.header-container.animate-in {
  opacity: 1;
  transform: translateY(0) scale(1);
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
  transition: background-color 0.2s, opacity 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}

.refresh-button.animate-in {
  opacity: 1;
  transform: translateY(0) scale(1);
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

/* 开屏动画效果 */
.section-animate {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
  transition: opacity 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.section-animate.animate-in {
  opacity: 1;
  transform: translateY(0) scale(1);
}

/* 子元素动画 */
:deep(.stats-grid) {
  opacity: 0;
  transform: translateY(10px) scale(0.98);
  transition: opacity 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.animate-in :deep(.stats-grid) {
  opacity: 1;
  transform: translateY(0) scale(1);
  transition-delay: 0.1s;
}

/* 卡片动画 */
:deep(.stat-card) {
  opacity: 0;
  transform: scale(0.9) translateY(10px);
  transition: opacity 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.3s, background-color 0.3s;
}

.animate-in :deep(.stat-card) {
  opacity: 1;
  transform: scale(1) translateY(0);
}

.animate-in :deep(.stat-card:nth-child(1)) {
  transition-delay: 0.15s;
}

.animate-in :deep(.stat-card:nth-child(2)) {
  transition-delay: 0.2s;
}

.animate-in :deep(.stat-card:nth-child(3)) {
  transition-delay: 0.25s;
}

.animate-in :deep(.stat-card:nth-child(4)) {
  transition-delay: 0.3s;
}

.animate-in :deep(.stat-card:nth-child(5)) {
  transition-delay: 0.35s;
}

.animate-in :deep(.stat-card:nth-child(6)) {
  transition-delay: 0.4s;
}

.animate-in :deep(.stat-card:nth-child(7)) {
  transition-delay: 0.45s;
}

.animate-in :deep(.stat-card:nth-child(8)) {
  transition-delay: 0.5s;
}

/* 日志条目动画 */
:deep(.log-entry) {
  opacity: 0;
  transform: translateX(-10px) scale(0.98);
  transition: opacity 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.animate-in :deep(.log-entry) {
  opacity: 1;
  transform: translateX(0) scale(1);
}

.animate-in :deep(.log-entry:nth-child(1)) {
  transition-delay: 0.15s;
}

.animate-in :deep(.log-entry:nth-child(2)) {
  transition-delay: 0.2s;
}

.animate-in :deep(.log-entry:nth-child(3)) {
  transition-delay: 0.25s;
}

.animate-in :deep(.log-entry:nth-child(4)) {
  transition-delay: 0.3s;
}

.animate-in :deep(.log-entry:nth-child(5)) {
  transition-delay: 0.35s;
}

.animate-in :deep(.log-entry:nth-child(n+6)) {
  transition-delay: 0.4s;
}

/* 添加飞入动画效果 */
@keyframes flyIn {
  0% {
    opacity: 0;
    transform: translateY(30px) scale(0.9);
  }
  50% {
    opacity: 0.5;
    transform: translateY(15px) scale(0.95);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes flyInFromLeft {
  0% {
    opacity: 0;
    transform: translateX(-20px) scale(0.9);
  }
  50% {
    opacity: 0.5;
    transform: translateX(-10px) scale(0.95);
  }
  100% {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

@keyframes flyInFromRight {
  0% {
    opacity: 0;
    transform: translateX(20px) scale(0.9);
  }
  50% {
    opacity: 0.5;
    transform: translateX(10px) scale(0.95);
  }
  100% {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

/* 应用飞入动画 */
.header-container.animate-in {
  animation: flyIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.section-animate.animate-in {
  animation: flyIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.animate-in :deep(.stat-card:nth-child(odd)) {
  animation: flyInFromLeft 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.animate-in :deep(.stat-card:nth-child(even)) {
  animation: flyInFromRight 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.animate-in :deep(.log-entry) {
  animation: flyInFromLeft 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

.refresh-button.animate-in {
  animation: flyIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
</style>