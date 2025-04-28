<script setup>
  import { useDashboardStore } from '../../stores/dashboard'
  import { computed, ref } from 'vue'
  
  const dashboardStore = useDashboardStore()
  const apiKeyStatsVisible = ref(false)
  // 存储每个API密钥的模型折叠状态
  const modelFoldState = ref({})
  
  // 分页相关
  const currentPage = ref(1)
  const itemsPerPage = 20
  
  // 重置对话框状态
  const showResetDialog = ref(false)
  const resetPassword = ref('')
  const resetError = ref('')
  const isResetting = ref(false)
  
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
      .map(([model, data]) => ({ 
        model, 
        calls: data.calls,
        tokens: data.tokens
      }))
      .sort((a, b) => b.calls - a.calls)
  }
  
  // 判断是否需要折叠
  const shouldFoldModels = (modelStats) => {
    return modelStats && Object.keys(modelStats).length > 3
  }
  
  // 打开重置对话框
  function openResetDialog() {
    showResetDialog.value = true
    resetPassword.value = ''
    resetError.value = ''
  }
  
  // 关闭重置对话框
  function closeResetDialog() {
    showResetDialog.value = false
    resetPassword.value = ''
    resetError.value = ''
  }
  
  // 重置统计数据
  async function resetStats() {
    if (!resetPassword.value) {
      resetError.value = '请输入密码'
      return
    }
    
    isResetting.value = true
    resetError.value = ''
    
    try {
      const response = await fetch('/api/reset-stats', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ password: resetPassword.value })
      })
      
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail || '重置失败')
      }
      
      // 重置成功，刷新数据
      await dashboardStore.fetchDashboardData()
      
      // 添加短暂延迟，确保后端数据已完全重置
      setTimeout(async () => {
        try {
          await dashboardStore.fetchDashboardData()
          console.log('重置后数据已刷新')
        } catch (error) {
          console.error('刷新数据失败:', error)
        } finally {
          closeResetDialog()
        }
      }, 1000) // 增加延迟时间到1秒
    } catch (error) {
      console.error('重置失败:', error)
      resetError.value = error.message || '重置失败，请检查密码是否正确'
    } finally {
      isResetting.value = false
    }
  }
  
  // 计算总页数
  const totalPages = computed(() => {
    if (!dashboardStore.apiKeyStats.length) return 0
    return Math.ceil(dashboardStore.apiKeyStats.length / itemsPerPage)
  })
  
  // 获取当前页的API密钥
  const paginatedApiKeys = computed(() => {
    if (!dashboardStore.apiKeyStats.length) return []
    
    const startIndex = (currentPage.value - 1) * itemsPerPage
    const endIndex = startIndex + itemsPerPage
    
    return dashboardStore.apiKeyStats.slice(startIndex, endIndex)
  })
  
  // 切换到下一页
  function nextPage() {
    if (currentPage.value < totalPages.value) {
      currentPage.value++
    }
  }
  
  // 切换到上一页
  function prevPage() {
    if (currentPage.value > 1) {
      currentPage.value--
    }
  }
  
  // 计算总调用次数
  const totalCalls = computed(() => {
    return dashboardStore.apiKeyStats.reduce((sum, key) => sum + key.calls_24h, 0)
  })
  
  // 计算总Token使用量
  const totalTokens = computed(() => {
    return dashboardStore.apiKeyStats.reduce((sum, key) => sum + key.total_tokens, 0)
  })
</script>
  
  <template>
    <div class="info-box">
      <div class="section-header">
        <h2 class="section-title">🟢 运行状态</h2>
        <div class="status-container">
          <p class="status">服务运行中</p>
        </div>
        <button class="reset-button" @click="openResetDialog" v-if="!dashboardStore.status.enableVertex">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
            <path d="M3 3v5h5"></path>
          </svg>
          重置次数
        </button>
      </div>
      <div class="vertex-notice" v-if="dashboardStore.status.enableVertex">
        <div class="notice-icon">ℹ️</div>
        <div class="notice-content">
          <h3 class="notice-title">Vertex 模式说明</h3>
          <p class="notice-text">当前项目处于 Vertex 模式，完全基于 gzzhongqi/vertex2openai 项目开发。目前处于初步适配阶段，统计功能正在逐步完善中。</p>
        </div>
      </div>
      <div class="stats-grid" v-if="!dashboardStore.status.enableVertex">
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
      
      <div class="api-key-stats-container" v-if="!dashboardStore.status.enableVertex">
        <h3 class="section-title fold-header" @click="toggleApiKeyStats">
          API调用统计
          <span :class="getFoldIconClass(apiKeyStatsVisible)">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </span>
        </h3>
        
        <!-- 收起时显示的总计信息 -->
        <div v-if="!apiKeyStatsVisible" class="stats-grid">
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
        
        <!-- 展开时显示的详细API密钥信息 -->
        <transition name="fold">
          <div v-if="apiKeyStatsVisible" class="fold-content">
            <!-- 总计信息 -->
            <div class="stats-summary">
              <div class="summary-item">
                <div class="summary-label">总调用次数</div>
                <div class="summary-value">{{ totalCalls.toLocaleString() }}</div>
              </div>
              <div class="summary-item">
                <div class="summary-label">总Token使用量</div>
                <div class="summary-value">{{ totalTokens.toLocaleString() }}</div>
              </div>
              <div class="summary-item">
                <div class="summary-label">API密钥数量</div>
                <div class="summary-value">{{ dashboardStore.apiKeyStats.length }}</div>
              </div>
            </div>
            
            <div class="api-key-stats-list">
              <div v-if="!dashboardStore.apiKeyStats.length" class="api-key-item">
                没有API密钥使用数据
              </div>
              <div v-for="(stat, index) in paginatedApiKeys" :key="index" class="api-key-item">
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
                
                <!-- 显示总token使用量 -->
                <div class="total-tokens">
                  <span class="total-tokens-label">总Token使用量:</span>
                  <span class="total-tokens-value">{{ stat.total_tokens.toLocaleString() }}</span>
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
                        <div class="model-info">
                          <div class="model-name">{{ modelStat.model }}</div>
                          <div class="model-count">
                            <span>{{ modelStat.calls }}</span>
                            <span class="model-usage-text">次调用</span>
                          </div>
                          <div class="model-tokens">{{ modelStat.tokens.toLocaleString() }} tokens</div>
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
            
            <!-- 分页控件 -->
            <div v-if="dashboardStore.apiKeyStats.length > itemsPerPage" class="pagination">
              <button 
                class="pagination-button" 
                :disabled="currentPage === 1"
                @click="prevPage"
              >
                上一页
              </button>
              <div class="pagination-info">
                第 {{ currentPage }} 页 / 共 {{ totalPages }} 页
              </div>
              <button 
                class="pagination-button" 
                :disabled="currentPage === totalPages"
                @click="nextPage"
              >
                下一页
              </button>
            </div>
          </div>
        </transition>
      </div>
      
      <!-- 重置对话框 -->
      <div v-if="showResetDialog" class="dialog-overlay">
        <div class="dialog">
          <h3>重置API调用统计</h3>
          <p>请输入密码以确认重置操作：</p>
          <input 
            type="password" 
            v-model="resetPassword" 
            placeholder="请输入密码"
            @keyup.enter="resetStats"
          />
          <div v-if="resetError" class="error-message">{{ resetError }}</div>
          <div class="dialog-buttons">
            <button class="cancel-button" @click="closeResetDialog">取消</button>
            <button 
              class="confirm-button" 
              @click="resetStats" 
              :disabled="isResetting"
            >
              {{ isResetting ? '重置中...' : '确认重置' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </template>
  
  <style scoped>
  .info-box {
    background-color: var(--card-background);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-xl);
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: var(--shadow-md);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
  }
  
  .info-box::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: var(--gradient-success);
    opacity: 0.8;
  }
  
  /* 移动端优化 - 减小外边距 */
  @media (max-width: 768px) {
    .info-box {
      margin-bottom: 12px;
      padding: 15px 10px;
      border-radius: var(--radius-lg);
    }
  }
  
  @media (max-width: 480px) {
    .info-box {
      margin-bottom: 8px;
      padding: 12px 8px;
      border-radius: var(--radius-md);
    }
  }
  
  /* 添加section-header样式 */
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    position: relative;
  }
  
  /* 状态容器样式 */
  .status-container {
    display: flex;
    align-items: center;
    justify-content: center;
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }
  
  /* 重置按钮样式 */
  .reset-button {
    display: flex;
    align-items: center;
    gap: 5px;
    background-color: var(--button-secondary);
    color: var(--button-secondary-text);
    border: none;
    border-radius: var(--radius-md);
    padding: 8px 12px;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    height: 100%;
    z-index: 1;
  }
  
  .reset-button::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
    transform: translateX(-100%);
    transition: transform 0.6s ease;
  }
  
  .reset-button:hover::before {
    transform: translateX(100%);
  }
  
  .reset-button:hover {
    background-color: var(--button-secondary-hover);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
  
  .reset-button svg {
    transition: transform 0.3s;
  }
  
  .reset-button:hover svg {
    transform: rotate(180deg);
  }
  
  /* 对话框样式 */
  .dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: flex-start;
    z-index: 1000;
    padding-top: 20px;
    backdrop-filter: blur(5px);
  }
  
  .dialog {
    background-color: var(--card-background);
    border-radius: var(--radius-xl);
    padding: 20px;
    width: 90%;
    max-width: 400px;
    box-shadow: var(--shadow-xl);
    margin-top: 20px;
    position: relative;
    overflow: hidden;
    animation: dialogAppear 0.3s ease forwards;
  }
  
  @keyframes dialogAppear {
    0% {
      opacity: 0;
      transform: translateY(-20px) scale(0.95);
    }
    100% {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }
  
  .dialog::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 4px;
    background: var(--gradient-primary);
  }
  
  .dialog h3 {
    margin-top: 0;
    margin-bottom: 10px;
    color: var(--color-heading);
    font-size: 1.2rem;
    font-weight: 600;
  }
  
  .dialog p {
    margin-bottom: 15px;
    color: var(--color-text);
    font-size: 14px;
    line-height: 1.5;
  }
  
  .dialog input {
    width: 100%;
    padding: 12px 16px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    margin-bottom: 15px;
    background-color: var(--color-background);
    color: var(--color-text);
    transition: all 0.3s ease;
    font-size: 14px;
  }
  
  .dialog input:focus {
    outline: none;
    border-color: var(--button-primary);
    box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.2);
  }
  
  .error-message {
    color: #ef4444;
    margin-bottom: 15px;
    font-size: 14px;
    padding: 8px 12px;
    background-color: rgba(239, 68, 68, 0.1);
    border-radius: var(--radius-md);
    border-left: 3px solid #ef4444;
  }
  
  .dialog-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }
  
  .cancel-button {
    background-color: var(--button-secondary);
    color: var(--button-secondary-text);
    border: none;
    border-radius: var(--radius-md);
    padding: 10px 18px;
    cursor: pointer;
    transition: all 0.3s ease;
    font-weight: 500;
  }
  
  .cancel-button:hover {
    background-color: var(--button-secondary-hover);
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
  }
  
  .confirm-button {
    background: var(--gradient-primary);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    padding: 10px 18px;
    cursor: pointer;
    transition: all 0.3s ease;
    font-weight: 500;
    box-shadow: var(--shadow-sm);
  }
  
  .confirm-button:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
  
  .confirm-button:disabled {
    opacity: 0.7;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }
  
  .status {
    color: #10b981;
    font-weight: bold;
    font-size: 16px;
    padding: 8px 12px;
    background-color: rgba(16, 185, 129, 0.1);
    border-radius: var(--radius-md);
    border-left: none;
    transition: all 0.3s ease;
    animation: pulse 2s infinite;
    margin: 0;
    white-space: nowrap;
  }
  
  @keyframes pulse {
    0% {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4);
    }
    70% {
      box-shadow: 0 0 0 10px rgba(16, 185, 129, 0);
    }
    100% {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
    }
  }
  
  .section-title {
    color: var(--color-heading);
    border-bottom: 1px solid var(--color-border);
    padding-bottom: 10px;
    margin-bottom: 20px;
    transition: all 0.3s ease;
    position: relative;
    font-weight: 600;
    margin: 0;
  }
  
  .section-title::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    width: 50px;
    height: 2px;
    background: var(--gradient-primary);
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
    border-radius: var(--radius-lg);
    text-align: center;
    box-shadow: var(--shadow-sm);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
    border: 1px solid var(--card-border);
  }
  
  .stat-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 4px;
    background: var(--gradient-secondary);
    opacity: 0;
    transition: opacity 0.3s ease;
  }
  
  .stat-card:hover::before {
    opacity: 1;
  }
  
  .stat-card:hover {
    transform: translateY(-5px);
    box-shadow: var(--shadow-md);
    border-color: var(--button-primary);
  }
  
  .stat-value {
    font-size: 24px;
    font-weight: bold;
    color: var(--button-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: all 0.3s ease;
    margin-bottom: 5px;
  }
  
  .stat-label {
    font-size: 14px;
    color: var(--color-text);
    margin-top: 5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: all 0.3s ease;
    opacity: 0.8;
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
    
    .status {
      font-size: 14px;
      padding: 6px 10px;
    }
    
    .reset-button {
      font-size: 12px;
      padding: 6px 10px;
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
    
    .status {
      font-size: 12px;
      padding: 4px 8px;
    }
    
    .reset-button {
      font-size: 11px;
      padding: 4px 8px;
    }
    
    .section-header {
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      position: relative;
      padding-top: 0;
    }
    
    .section-title {
      font-size: 14px;
      margin-right: auto;
    }
    
    .status-container {
      position: static;
      transform: none;
      margin: 0;
    }
    
    .reset-button {
      align-self: center;
    }
  }
  
  /* API密钥统计样式 */
  .api-key-stats-container {
    margin-top: 20px;
  }
  
  /* 总计信息样式 */
  .stats-summary {
    display: flex;
    justify-content: space-between;
    margin-bottom: 20px;
    background-color: var(--color-background-mute);
    border-radius: var(--radius-lg);
    padding: 15px;
    border: 1px solid var(--card-border);
  }
  
  .summary-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
  }
  
  .summary-label {
    font-size: 12px;
    color: var(--color-text);
    opacity: 0.8;
    margin-bottom: 5px;
  }
  
  .summary-value {
    font-size: 18px;
    font-weight: 600;
    color: var(--button-primary);
  }
  
  @media (max-width: 768px) {
    .stats-summary {
      flex-direction: column;
      gap: 10px;
      padding: 10px;
    }
    
    .summary-item {
      flex-direction: row;
      justify-content: space-between;
      width: 100%;
    }
    
    .summary-label {
      margin-bottom: 0;
    }
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
    background-color: var(--stats-item-bg);
    border-radius: var(--radius-lg);
    padding: 15px;
    box-shadow: var(--shadow-sm);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
    border: 1px solid var(--card-border);
  }
  
  .api-key-item::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 4px;
    background: var(--gradient-info);
    opacity: 0;
    transition: opacity 0.3s ease;
  }
  
  .api-key-item:hover::before {
    opacity: 1;
  }
  
  .api-key-item:hover {
    transform: translateY(-3px);
    box-shadow: var(--shadow-md);
    border-color: var(--button-primary);
  }
  
  .api-key-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  
  .api-key-name {
    font-weight: bold;
    color: var(--color-heading);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 50%;
    transition: all 0.3s ease;
  }
  
  .api-key-usage {
    display: flex;
    align-items: center;
    gap: 10px;
    white-space: nowrap;
  }
  
  .api-key-count {
    font-weight: bold;
    color: var(--button-primary);
    transition: all 0.3s ease;
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
    background-color: var(--color-background-soft);
    border-radius: var(--radius-full);
    overflow: hidden;
    transition: all 0.3s ease;
    margin: 10px 0;
  }
  
  .progress-bar {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 0.5s ease, background-color 0.3s;
    position: relative;
    overflow: hidden;
  }
  
  .progress-bar::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
    transform: translateX(-100%);
    animation: progressShine 2s infinite;
  }
  
  @keyframes progressShine {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(100%);
    }
  }
  
  .progress-bar.low {
    background: var(--gradient-success);
  }
  
  .progress-bar.medium {
    background: var(--gradient-warning);
  }
  
  .progress-bar.high {
    background: var(--gradient-danger);
  }
  
  /* 模型统计样式 */
  .model-stats-container {
    margin-top: 10px;
    border-top: 1px dashed var(--color-border);
    padding-top: 10px;
    transition: all 0.3s ease;
  }
  
  .model-stats-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    user-select: none;
    margin-bottom: 8px;
    color: var(--color-heading);
    font-size: 14px;
    transition: all 0.3s ease;
    padding: 5px 8px;
    border-radius: var(--radius-md);
  }
  
  .model-stats-header:hover {
    background-color: var(--color-background-mute);
  }
  
  .model-stats-title {
    font-weight: 600;
  }
  
  .model-stats-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  
  .model-stat-item {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 10px;
    background-color: var(--color-background-mute);
    border-radius: var(--radius-md);
    font-size: 13px;
    transition: all 0.3s ease;
    border: 1px solid transparent;
  }
  
  .model-stat-item:hover {
    transform: translateX(5px);
    box-shadow: var(--shadow-sm);
    border-color: var(--button-primary);
  }
  
  .model-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 100%;
  }
  
  .model-name {
    font-weight: 500;
    color: var(--color-heading);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
    transition: all 0.3s ease;
  }
  
  .model-count {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--button-primary);
    font-weight: 600;
    transition: all 0.3s ease;
  }
  
  .model-usage-text {
    color: var(--color-text);
    font-weight: normal;
    font-size: 12px;
    transition: all 0.3s ease;
    opacity: 0.8;
  }
  
  .model-tokens {
    font-size: 12px;
    color: var(--color-text);
    opacity: 0.8;
    transition: all 0.3s ease;
  }
  
  .view-more-models {
    text-align: center;
    color: var(--button-primary);
    font-size: 12px;
    cursor: pointer;
    padding: 8px;
    margin-top: 5px;
    border-radius: var(--radius-md);
    background-color: rgba(79, 70, 229, 0.05);
    transition: all 0.3s ease;
    border: 1px dashed var(--button-primary);
  }
  
  .view-more-models:hover {
    background-color: rgba(79, 70, 229, 0.1);
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
  }
  
  /* 折叠动画和UI优化 */
  .fold-header {
    cursor: pointer;
    user-select: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: all 0.3s ease;
    border-radius: var(--radius-md);
    padding: 8px 12px;
    background-color: var(--color-background-mute);
    margin-bottom: 15px;
  }
  
  .fold-header:hover {
    background-color: var(--color-background-soft);
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
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
      padding: 8px;
    }
  }
  
  .vertex-notice {
    background-color: var(--color-background-soft);
    border-radius: var(--radius-lg);
    padding: 16px;
    margin: 20px 0;
    display: flex;
    gap: 16px;
    align-items: flex-start;
    border: 1px solid var(--color-border);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
  }
  
  .vertex-notice::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: var(--gradient-info);
    opacity: 0.8;
  }
  
  .vertex-notice:hover {
    transform: translateY(-3px);
    box-shadow: var(--shadow-md);
    border-color: var(--button-primary);
  }
  
  .notice-icon {
    font-size: 24px;
    background-color: var(--color-background-mute);
    padding: 8px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 40px;
    height: 40px;
    transition: all 0.3s ease;
    box-shadow: var(--shadow-sm);
  }
  
  .notice-content {
    flex: 1;
  }
  
  .notice-title {
    color: var(--color-heading);
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 8px 0;
    transition: all 0.3s ease;
  }
  
  .notice-text {
    color: var(--color-text);
    font-size: 14px;
    line-height: 1.5;
    margin: 0;
    transition: all 0.3s ease;
  }
  
  @media (max-width: 768px) {
    .vertex-notice {
      padding: 12px;
      gap: 12px;
    }
    
    .notice-icon {
      font-size: 20px;
      min-width: 32px;
      height: 32px;
      padding: 6px;
    }
    
    .notice-title {
      font-size: 14px;
      margin-bottom: 6px;
    }
    
    .notice-text {
      font-size: 12px;
    }
  }
  
  /* 修改总token使用量样式 */
  .total-tokens {
    margin-top: 6px;
    padding: 8px 12px;
    background-color: var(--color-background-mute);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.3s ease;
    border: 1px solid var(--card-border);
  }
  
  .total-tokens:hover {
    background-color: var(--color-background-soft);
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
    border-color: var(--button-primary);
  }
  
  .total-tokens-label {
    font-size: 11px;
    color: var(--color-text);
    opacity: 0.8;
    white-space: nowrap;
    transition: all 0.3s ease;
  }
  
  .total-tokens-value {
    font-size: 13px;
    font-weight: 600;
    color: var(--button-primary);
    transition: all 0.3s ease;
  }
  
  /* 移动端优化 */
  @media (max-width: 768px) {
    .total-tokens {
      margin-top: 4px;
      padding: 6px 8px;
    }
    
    .total-tokens-label {
      font-size: 10px;
    }
    
    .total-tokens-value {
      font-size: 11px;
    }
  }
  
  /* 分页控件样式 */
  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    margin-top: 20px;
    gap: 15px;
  }
  
  .pagination-button {
    background-color: var(--button-secondary);
    color: var(--button-secondary-text);
    border: none;
    border-radius: var(--radius-md);
    padding: 8px 16px;
    cursor: pointer;
    transition: all 0.3s ease;
    font-weight: 500;
  }
  
  .pagination-button:hover:not(:disabled) {
    background-color: var(--button-secondary-hover);
    transform: translateY(-2px);
    box-shadow: var(--shadow-sm);
  }
  
  .pagination-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .pagination-info {
    font-size: 14px;
    color: var(--color-text);
  }
  
  @media (max-width: 768px) {
    .pagination {
      flex-direction: column;
      gap: 10px;
    }
    
    .pagination-button {
      width: 100%;
    }
  }
</style>