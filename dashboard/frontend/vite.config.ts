import { resolve } from 'node:path'

import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  appType: 'mpa',
  base: '/',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '^/api/admin': {
        target: 'http://127.0.0.1:8001',
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
      },
    },
  },
  build: {
    assetsDir: 'assets',
    rolldownOptions: {
      input: {
        next: resolve(import.meta.dirname, 'next/index.html'),
        admin: resolve(import.meta.dirname, 'admin/index.html'),
      },
    },
  },
  test: {
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
