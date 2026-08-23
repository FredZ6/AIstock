import { defineConfig } from '@playwright/test'

const webDataMode = process.env.WEB_DATA_MODE ?? 'fixture'
const webPort = process.env.PLAYWRIGHT_WEB_PORT ?? '3000'
const apiBaseUrl = process.env.API_BASE_URL

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  projects: [
    {
      name: 'desktop-chrome',
      use: { channel: 'chrome', viewport: { height: 900, width: 1440 } },
    },
    {
      name: 'mobile-chrome',
      use: { channel: 'chrome', hasTouch: true, isMobile: true, viewport: { height: 852, width: 393 } },
    },
  ],
  use: { baseURL: `http://127.0.0.1:${webPort}` },
  webServer: {
    command: `pnpm dev --hostname 127.0.0.1 --port ${webPort}`,
    env: {
      WEB_DATA_MODE: webDataMode,
      ...(apiBaseUrl ? { API_BASE_URL: apiBaseUrl } : {}),
    },
    reuseExistingServer: !process.env.CI,
    url: `http://127.0.0.1:${webPort}`,
  },
})
