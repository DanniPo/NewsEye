/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The read-only API (uvicorn backend.api.main:app). The development and preview
// servers pass /api through to it, so the browser sees one origin and needs no CORS.
const api = process.env.NEWSEYE_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { '/api': api } },
  preview: { port: 4173, strictPort: true, proxy: { '/api': api } },
  build: { sourcemap: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    restoreMocks: true,
    testTimeout: 20_000,
  },
})
