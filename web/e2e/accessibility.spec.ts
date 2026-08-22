import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const pages = [
  '/',
  '/watchlist',
  '/research/NVDA',
  '/runs/latest',
  '/portfolio',
  '/alerts',
  '/weekly-review',
  '/eval',
] as const

test.beforeEach(async ({ page }) => {
  // TradingView is a separately owned, cross-origin surface; keep the owned-DOM gate deterministic.
  await page.route(/tradingview\.com/, (route) => route.abort())
})

test('all product pages have no serious or critical automated accessibility violations', async ({ page }) => {
  for (const path of pages) {
    await page.goto(path)
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      // TradingView owns the cross-origin iframe document; scan our labelled host surface only.
      .exclude('iframe')
      .analyze()
    const severe = results.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical')
    expect(severe, `${path}: ${severe.map(({ id }) => id).join(', ')}`).toEqual([])
  }
})
