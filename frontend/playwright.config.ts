import { defineConfig } from '@playwright/test'

// End-to-end checks against the real API and database: run them on a machine
// with the database (DB_PASSWORD set). They reuse servers already running, or
// start the API and the development server themselves.
const python = process.env.NEWSEYE_PYTHON
  ?? (process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python')

export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    // the installed Edge, so no browser download is needed
    channel: process.env.PLAYWRIGHT_CHANNEL ?? 'msedge',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `${python} -m uvicorn backend.api.main:app --port 8000`,
      cwd: '..',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'npx vite --port 5173 --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
})
