import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useDashboardStore = defineStore('dashboard', () => {
  // 状态
  const status = ref({
    keyCount: 0,
    modelCount: 0,
    retryCount: 0,
    last24hCalls: 0,
    hourlyCalls: 0,
    minuteCalls: 0
  })

  const config = ref({
    maxRequestsPerMinute: 0,
    maxRequestsPerDayPerIp: 0,
    currentTime: '',
    fakeStreaming: false,
    fakeStreamingInterval: 0,
    randomString: false,
    localVersion: '',
    remoteVersion: '',
    hasUpdate: false
  })

  const apiKeyStats = ref([])
  const logs = ref([])
  const isRefreshing = ref(false)

  // 获取仪表盘数据
  async function fetchDashboardData() {
    if (isRefreshing.value) return // 防止重复请求
    
    isRefreshing.value = true
    try {
      const response = await fetch('/api/dashboard-data')
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      updateDashboardData(data)
    } catch (error) {
      console.error('获取数据失败:', error)
    } finally {
      isRefreshing.value = false
    }
  }

  // 更新仪表盘数据
  function updateDashboardData(data) {
    // 更新状态数据
    status.value = {
      keyCount: data.key_count || 0,
      modelCount: data.model_count || 0,
      retryCount: data.retry_count || 0,
      last24hCalls: data.last_24h_calls || 0,
      hourlyCalls: data.hourly_calls || 0,
      minuteCalls: data.minute_calls || 0
    }

    // 更新配置数据
    config.value = {
      maxRequestsPerMinute: data.max_requests_per_minute || 0,
      maxRequestsPerDayPerIp: data.max_requests_per_day_per_ip || 0,
      currentTime: data.current_time || '',
      fakeStreaming: data.fake_streaming || false,
      fakeStreamingInterval: data.fake_streaming_interval || 0,
      randomString: data.random_string || false,
      localVersion: data.local_version || '',
      remoteVersion: data.remote_version || '',
      hasUpdate: data.has_update || false
    }

    // 更新API密钥统计
    if (data.api_key_stats) {
      apiKeyStats.value = data.api_key_stats
    }

    // 更新日志
    if (data.logs) {
      logs.value = data.logs
    }
  }

  return {
    status,
    config,
    apiKeyStats,
    logs,
    isRefreshing,
    fetchDashboardData
  }
})