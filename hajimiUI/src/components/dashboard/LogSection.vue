<script setup>
import { useDashboardStore } from '../../stores/dashboard'
import { ref, watch, nextTick } from 'vue'

const dashboardStore = useDashboardStore()
const currentFilter = ref('ALL')
const logContainer = ref(null)

// 过滤日志
function filterLogs(level) {
  currentFilter.value = level
}

// 监听日志变化，保持滚动位置
watch(() => dashboardStore.logs, async () => {
  await nextTick()
  if (logContainer.value) {
    // 滚动到底部
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}, { deep: true })
</script>

<template>
  <div class="info-box">
    <h2 class="section-title">📋 系统日志</h2>
    <div class="log-filter">
      <button 
        v-for="level in ['ALL', 'INFO', 'WARNING', 'ERROR']" 
        :key="level"
        :class="{ active: currentFilter === level }"
        @click="filterLogs(level)"
      >
        {{ level === 'ALL' ? '全部' : level === 'INFO' ? '信息' : level === 'WARNING' ? '警告' : '错误' }}
      </button>
    </div>
    <div class="log-container" ref="logContainer">
      <div 
        v-for="(log, index) in dashboardStore.logs" 
        :key="index"
        class="log-entry"
        :class="log.level"
        :style="{ display: currentFilter === 'ALL' || log.level === currentFilter ? 'block' : 'none' }"
      >
        <span class="log-timestamp">{{ log.timestamp }}</span>
        <span class="log-level" :class="log.level">{{ log.level }}</span>
        <span class="log-message">
          <template v-if="log.key !== 'N/A'">[{{ log.key }}]</template>
          <template v-if="log.request_type !== 'N/A'">{{ log.request_type }}</template>
          <template v-if="log.model !== 'N/A'">[{{ log.model }}]</template>
          <template v-if="log.status_code !== 'N/A'">{{ log.status_code }}</template>
          : {{ log.message }}
          <template v-if="log.error_message">
            - {{ log.error_message }}
          </template>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.info-box {
  background-color: #fff;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
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
  color: #495057;
  border-bottom: 1px solid #dee2e6;
  padding-bottom: 10px;
  margin-bottom: 20px;
}

.log-filter {
  display: flex;
  justify-content: center;
  margin-bottom: 15px;
  gap: 10px;
  flex-wrap: wrap;
}

.log-filter button {
  padding: 5px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background-color: #f8f9fa;
  cursor: pointer;
  min-width: 60px;
}

.log-filter button.active {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}

/* 移动端优化 */
@media (max-width: 768px) {
  .log-filter {
    gap: 6px;
    margin-bottom: 12px;
  }
  
  .log-filter button {
    padding: 4px 8px;
    font-size: 12px;
    min-width: 50px;
  }
}

/* 小屏幕手机进一步优化 */
@media (max-width: 480px) {
  .log-filter {
    gap: 4px;
    margin-bottom: 10px;
  }
  
  .log-filter button {
    padding: 3px 6px;
    font-size: 11px;
    min-width: 40px;
  }
}

.log-container {
  background-color: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 15px;
  margin-top: 20px;
  max-height: 500px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 14px;
  line-height: 1.5;
}

.log-entry {
  margin-bottom: 8px;
  padding: 8px;
  border-radius: 4px;
  word-break: break-word;
}

.log-entry.INFO {
  background-color: #e8f4f8;
  border-left: 4px solid #17a2b8;
}

.log-entry.WARNING {
  background-color: #fff3cd;
  border-left: 4px solid #ffc107;
}

.log-entry.ERROR {
  background-color: #f8d7da;
  border-left: 4px solid #dc3545;
}

.log-entry.DEBUG {
  background-color: #d1ecf1;
  border-left: 4px solid #17a2b8;
}

.log-timestamp {
  color: #6c757d;
  font-size: 12px;
  margin-right: 10px;
}

.log-level {
  font-weight: bold;
  margin-right: 10px;
}

.log-level.INFO {
  color: #17a2b8;
}

.log-level.WARNING {
  color: #ffc107;
}

.log-level.ERROR {
  color: #dc3545;
}

.log-level.DEBUG {
  color: #17a2b8;
}

.log-message {
  color: #212529;
}

@media (max-width: 768px) {
  .log-container {
    padding: 10px;
    font-size: 13px;
  }
  
  .log-entry {
    padding: 6px;
    margin-bottom: 6px;
  }
  
  .log-timestamp {
    font-size: 11px;
    display: block;
    margin-bottom: 3px;
  }
}

@media (max-width: 480px) {
  .log-container {
    padding: 8px;
    font-size: 12px;
  }
  
  .log-entry {
    padding: 5px;
    margin-bottom: 5px;
  }
  
  .log-timestamp {
    font-size: 10px;
  }
  
  .log-level {
    margin-right: 5px;
  }
}
</style>