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
    // 生成的静态资源放在 assets 目录下
    assetsDir: '',
    // 生成 index.html 到 templates 目录
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: '[name].js',
        assetFileNames: '[name].[ext]'
      }
    },
    // 将 index.html 输出到 templates 目录
    emptyOutDir: true
  },
})
