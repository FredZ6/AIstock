import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'server-only': new URL('./tests/server-only.ts', import.meta.url).pathname,
    },
  },
  test: {
    environment: 'jsdom',
    exclude: ['e2e/**', '**/node_modules/**', '**/.next/**'],
    setupFiles: ['./tests/setup.ts'],
  },
})
