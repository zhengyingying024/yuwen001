import { fileURLToPath, URL } from 'node:url'
import { resolve, dirname } from 'node:path'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// 获取 __dirname 等效值
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// https://vite.dev/config/
export default defineConfig({
  base: '/assets/',  // 设置基础路径为 /assets/
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  build: {
    // 输出目录设置为 FastAPI 应用的静态文件目录
    outDir: resolve(__dirname, '../app/templates/assets'),
    // 不生成 HTML 文件，我们将在 build.js 中手动创建
    emptyOutDir: true,
    // 配置输出文件名
    rollupOptions: {
      output: {
        entryFileNames: 'main.js',
        chunkFileNames: '[name].js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name === 'style.css') {
            return 'main.css';
          }
          return '[name].[ext]';
        }
      }
    }
  },
})
