import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api/products': { target: 'http://localhost:8001', rewrite: (p) => p.replace(/^\/api\/products/, '/products') },
      '/api/orders': { target: 'http://localhost:8002', rewrite: (p) => p.replace(/^\/api\/orders/, '/orders') },
      '/api/analytics': { target: 'http://localhost:8003', rewrite: (p) => p.replace(/^\/api\/analytics/, '/analytics') },
    },
  },
})
