import { defineConfig, devices } from '@playwright/test'

const PORT = 4173
// Vite binds to `localhost`, which resolves to ::1 on some machines.
const APP_URL = `http://localhost:${PORT}`

export default defineConfig({
  testDir: './e2e',
  // e2e/real 打真后端，需要自己的两条 webServer，见 playwright.real.config.ts。
  testIgnore: /[\\/]e2e[\\/]real[\\/]/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: APP_URL,
    trace: 'retain-on-failure',
    locale: 'zh-CN',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run dev -- --port ${PORT} --strictPort`,
    url: APP_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
