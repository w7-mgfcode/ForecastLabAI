import path from 'path'
import { defineConfig } from 'vitest/config'

// Vitest configuration. Kept separate from vite.config.ts so the app build
// (`tsc -b && vite build`) is unaffected by test tooling.
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
