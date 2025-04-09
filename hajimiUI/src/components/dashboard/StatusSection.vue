<script setup>
  import { useDashboardStore } from '../../stores/dashboard'
  import { computed, ref } from 'vue'
  
  const dashboardStore = useDashboardStore()
  const apiKeyStatsVisible = ref(true)
  // 存储每个API密钥的模型折叠状态
  const modelFoldState = ref({})
  
  // 切换API密钥统计显示/隐藏
  function toggleApiKeyStats() {
    apiKeyStatsVisible.value = !apiKeyStatsVisible.value
  }
  
  // 切换模型详情的折叠状态
  function toggleModelFold(apiKeyId) {
    if (!modelFoldState.value[apiKeyId]) {
      modelFoldState.value[apiKeyId] = true
    } else {
      modelFoldState.value[apiKeyId] = !modelFoldState.value[apiKeyId]
    }
  }
  
  // 获取折叠图标类
  const getFoldIconClass = (isVisible) => {
    return isVisible ? 'fold-icon rotated' : 'fold-icon'
  }
  
  // 计算进度条颜色类
  const getProgressBarClass = (usagePercent) => {
    if (usagePercent > 75) return 'high'
    if (usagePercent > 50) return 'medium'
    return 'low'
  }
  
  // 获取模型列表并按使用次数排序
  const getModelStats = (modelStats) => {
    if (!modelStats) return []
    
    return Object.entries(modelStats)
      .map(([model, count]) => ({ model, count }))
      .sort((a, b) => b.count - a.count)
  }
  
  // 判断是否需要折叠
  const shouldFoldModels = (modelStats) => {
    return modelStats && Object.keys(modelStats).length > 3
  }
</script>
  
  <template>
    <div class="info-box">
      <h2 class="section-title">🟢 运行状态</h2>
      <p class="status">服务运行中</p>
      
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">{{ dashboardStore.status.keyCount }}</div>
          <div class="stat-label">可用密钥数量</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ dashboardStore.status.modelCount }}</div>
          <div class="stat-label">可用模型数量</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ dashboardStore.status.retryCount }}</div>
          <div class="stat-label">最大重试次数</div>
        </div>
      </div>
      
      <h3 class="section-title">API调用统计</h3>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">{{ dashboardStore.status.last24hCalls }}</div>
          <div class="stat-label">24小时调用次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ dashboardStore.status.hourlyCalls }}</div>
          <div class="stat-label">小时调用次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ dashboardStore.status.minuteCalls }}</div>
          <div class="stat-label">分钟调用次数</div>
        </div>
      </div>
      
      <div class="api-key-stats-container">
        <h3 class="section-title fold-header" @click="toggleApiKeyStats">
          API密钥使用统计
          <span :class="getFoldIconClass(apiKeyStatsVisible)">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </span>
        </h3>
        <transition name="fold">
          <div v-if="apiKeyStatsVisible" class="fold-content">
          <div class="api-key-stats-list">
            <div v-if="!dashboardStore.apiKeyStats.length" class="api-key-item">
              没有API密钥使用数据
            </div>
            <div v-for="(stat, index) in dashboardStore.apiKeyStats" :key="index" class="api-key-item">
              <div class="api-key-header">
                <div class="api-key-name">API密钥: {{ stat.api_key }}</div>
                <div class="api-key-usage">
                  <span class="api-key-count">{{ stat.calls_24h }}</span> /
                  <span class="api-key-limit">{{ stat.limit }}</span>
                  <span class="api-key-percent">({{ stat.usage_percent }}%)</span>
                </div>
              </div>
              <div class="progress-container">
                <div
                  class="progress-bar"
                  :class="getProgressBarClass(stat.usage_percent)"
                  :style="{ width: Math.min(stat.usage_percent, 100) + '%' }"
                ></div>
              </div>
              
              <!-- 模型使用统计 -->
              <div v-if="stat.model_stats && Object.keys(stat.model_stats).length > 0" class="model-stats-container">
                <div class="model-stats-header" @click="toggleModelFold(stat.api_key)">
                  <span class="model-stats-title">模型使用统计</span>
                  <span :class="getFoldIconClass(modelFoldState[stat.api_key])">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                  </span>
                </div>
                
                <transition name="fold">
                  <div v-if="modelFoldState[stat.api_key]" class="model-stats-list fold-content">
                    <!-- 显示所有模型或前三个模型 -->
                    <div v-for="(modelStat, mIndex) in getModelStats(stat.model_stats).slice(0, shouldFoldModels(stat.model_stats) && !modelFoldState[stat.api_key] ? 3 : undefined)" :key="mIndex" class="model-stat-item">
                      <div class="model-name">{{ modelStat.model }}</div>
                      <div class="model-count">
                        <span>{{ modelStat.count }}</span>
                        <span class="model-usage-text">次调用</span>
                      </div>
                    </div>
                    
                    <!-- 显示"查看更多"按钮，如果模型数量超过3个且未展开全部 -->
                    <div
                      v-if="shouldFoldModels(stat.model_stats) && getModelStats(stat.model_stats).length > 3"
                      class="view-more-models"
                      @click="toggleModelFold(stat.api_key)"
                    >
                      {{ modelFoldState[stat.api_key] ? '收起' : '查看更多模型' }}
                    </div>
                  </div>
                </transition>
              </div>
            </div>
          </div>
          </div>
        </transition>
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
  
  .status {
    color: #28a745;
    font-weight: bold;
    font-size: 18px;
    margin-bottom: 20px;
    text-align: center;
  }
  
  .section-title {
    color: #495057;
    border-bottom: 1px solid #dee2e6;
    padding-bottom: 10px;
    margin-bottom: 20px;
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
    background-color: #e9ecef;
    padding: 15px;
    border-radius: 8px;
    text-align: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    transition: transform 0.2s;
  }
  
  .stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
  }
  
  .stat-value {
    font-size: 24px;
    font-weight: bold;
    color: #007bff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  .stat-label {
    font-size: 14px;
    color: #6c757d;
    margin-top: 5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
  
  /* API密钥统计样式 */
  .api-key-stats-container {
    margin-top: 20px;
  }
  
  .api-key-stats-list {
    display: grid;
    grid-template-columns: repeat(3, 1fr); /* 电脑上显示为三列 */
    gap: 15px;
    margin-top: 15px;
  }
  
  /* 在中等屏幕上显示为两列 */
  @media (max-width: 992px) {
    .api-key-stats-list {
      grid-template-columns: repeat(2, 1fr);
    }
  }
  
  /* 在小屏幕上显示为一列 */
  @media (max-width: 576px) {
    .api-key-stats-list {
      grid-template-columns: 1fr;
    }
  }
  
  .api-key-item {
    background-color: #f8f9fa;
    border-radius: 8px;
    padding: 15px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  }
  
  .api-key-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  
  .api-key-name {
    font-weight: bold;
    color: #495057;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 50%;
  }
  
  .api-key-usage {
    display: flex;
    align-items: center;
    gap: 10px;
    white-space: nowrap;
  }
  
  .api-key-count {
    font-weight: bold;
    color: #007bff;
  }
  
  /* 移动端优化 - 更紧凑的API密钥项 */
  @media (max-width: 768px) {
    .api-key-item {
      padding: 8px;
    }
    
    .api-key-header {
      margin-bottom: 6px;
    }
    
    .api-key-name {
      font-size: 12px;
    }
    
    .api-key-usage {
      font-size: 12px;
      gap: 5px;
    }
  }
  
  /* 小屏幕手机进一步优化 */
  @media (max-width: 480px) {
    .api-key-item {
      padding: 6px;
    }
    
    .api-key-name {
      font-size: 11px;
      max-width: 45%;
    }
    
    .api-key-usage {
      font-size: 11px;
      gap: 3px;
    }
  }
  
  .progress-container {
    width: 100%;
    height: 10px;
    background-color: #e9ecef;
    border-radius: 5px;
    overflow: hidden;
  }
  
  .progress-bar {
    height: 100%;
    border-radius: 5px;
    transition: width 0.3s ease;
  }
  
  .progress-bar.low {
    background-color: #28a745; /* 绿色 - 低使用率 */
  }
  
  .progress-bar.medium {
    background-color: #ffc107; /* 黄色 - 中等使用率 */
  }
  
  .progress-bar.high {
    background-color: #dc3545; /* 红色 - 高使用率 */
  }
  
  /* 模型统计样式 */
  .model-stats-container {
    margin-top: 10px;
    border-top: 1px dashed #dee2e6;
    padding-top: 10px;
  }
  
  .model-stats-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    user-select: none;
    margin-bottom: 8px;
    color: #495057;
    font-size: 14px;
  }
  
  .model-stats-title {
    font-weight: 600;
  }
  
  .model-stats-toggle {
    font-size: 12px;
  }
  
  .model-stats-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  
  .model-stat-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 10px;
    background-color: #f1f3f5;
    border-radius: 4px;
    font-size: 13px;
  }
  
  .model-name {
    font-weight: 500;
    color: #495057;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 60%;
  }
  
  .model-count {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #007bff;
    font-weight: 600;
  }
  
  .model-usage-text {
    color: #6c757d;
    font-weight: normal;
    font-size: 12px;
  }
  
  .model-progress-container {
    width: 60px;
    height: 6px;
    background-color: #e9ecef;
    border-radius: 3px;
    overflow: hidden;
    margin-left: 5px;
  }
  
  .model-progress-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
  }
  
  .view-more-models {
    text-align: center;
    color: #007bff;
    font-size: 12px;
    cursor: pointer;
    padding: 8px;
    margin-top: 5px;
    border-radius: 4px;
    background-color: rgba(0, 123, 255, 0.05);
    transition: all 0.2s ease;
  }
  
  .view-more-models:hover {
    background-color: rgba(0, 123, 255, 0.1);
    transform: translateY(-1px);
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
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
    background-color: rgba(0, 0, 0, 0.03);
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
  
  /* 模型统计项目悬停效果 */
  .model-stat-item {
    transition: transform 0.2s, box-shadow 0.2s;
  }
  
  .model-stat-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }
  
  /* 移动端优化 */
  @media (max-width: 768px) {
    .model-stats-container {
      margin-top: 8px;
      padding-top: 8px;
    }
    
    .model-stats-header {
      font-size: 12px;
      margin-bottom: 6px;
    }
    
    .model-stat-item {
      padding: 4px 8px;
      font-size: 11px;
    }
    
    .model-progress-container {
      width: 40px;
      height: 4px;
    }
  }
</style>