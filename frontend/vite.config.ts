import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // 真后端 e2e 会把它指到自己起的一次性服务上；默认仍是开发中的 :8000。
        target: process.env.E2E_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
