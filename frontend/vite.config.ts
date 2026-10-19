import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies the backend so one tunnel URL (pointing at :5173) serves both.
// HC_API_TARGET points the proxy at another backend, for example a mock during UI review.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {}
const api = env.HC_API_TARGET || 'http://127.0.0.1:8000'
// The quiz runs as its own app until the main backend mounts backend.quiz.api.router.
const quiz = env.HC_QUIZ_TARGET || 'http://127.0.0.1:8001'
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api/quiz': { target: quiz, changeOrigin: true },
      '/api': { target: api, changeOrigin: true },
      '/ws': { target: api.replace(/^http/, 'ws'), ws: true },
    },
  },
})
