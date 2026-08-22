import { defineConfig } from '@playwright/test'

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
  use: { baseURL: 'http://127.0.0.1:3000' },
  webServer: {
    command: 'pnpm dev --hostname 127.0.0.1',
    reuseExistingServer: !process.env.CI,
    url: 'http://127.0.0.1:3000',
  },
})
