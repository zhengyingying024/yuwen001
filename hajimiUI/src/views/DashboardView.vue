<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import StatusSection from '../components/dashboard/StatusSection.vue'
import ConfigSection from '../components/dashboard/ConfigSection.vue'
import LogSection from '../components/dashboard/LogSection.vue'
import { useDashboardStore } from '../stores/dashboard'

const dashboardStore = useDashboardStore()
const refreshInterval = ref(null)

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
</script>

<template>
  <div class="dashboard">
    <h1>🤖 Gemini API 代理服务</h1>
    
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
  background-color: #f8f9fa;
  margin: 0;
  padding: 0;
}

.dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

h1 {
  color: #333;
  text-align: center;
  margin: 20px 0;
}

.refresh-button {
  display: block;
  margin: 20px auto;
  padding: 10px 20px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 16px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.refresh-button:hover {
  background-color: #0069d9;
}
</style>