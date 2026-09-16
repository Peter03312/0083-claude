import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// 本地开发直连 api:8000（compose 内）或 localhost:8000。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '', '')
  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 4173,
    },
  }
})
