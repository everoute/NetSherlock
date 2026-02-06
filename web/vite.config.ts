import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig(({ command, mode }) => {
  // Load environment variables from .env files
  // loadEnv takes into account .env.local and .env.{mode}.local overrides
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 3000,
      proxy: {
        // Proxy API endpoints to backend (loaded from .env)
        '^/health': {
          target: apiUrl,
          changeOrigin: true,
        },
        '^/diagnose': {
          target: apiUrl,
          changeOrigin: true,
        },
        '^/diagnosis': {
          target: apiUrl,
          changeOrigin: true,
        },
        '^/diagnoses': {
          target: apiUrl,
          changeOrigin: true,
        },
        '^/chat': {
          target: apiUrl,
          changeOrigin: true,
        },
      },
    },
  }
})
