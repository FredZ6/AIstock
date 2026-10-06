import { expect, test } from '@playwright/test'

test('every API page keeps backend failure explicit without fixture fallback', async ({ page }) => {
  test.skip(process.env.WEB_DATA_MODE !== 'api' || process.env.EXPECT_API_FAILURE !== '1', 'Requires controlled unavailable API')
  for (const path of ['/', '/watchlist', '/research/NVDA', '/runs/latest', '/portfolio', '/alerts', '/weekly-review', '/eval']) {
    await page.goto(path)
    await expect(page.getByRole('alert', { name: /unavailable/i })).toBeVisible()
    await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
    await expect(page.getByText(/Frozen synthetic/i)).toHaveCount(0)
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  }
})

test.describe('Watchlist refresh failure matrix', () => {
  test.skip(process.env.WEB_DATA_MODE !== 'api' || process.env.EXPECT_API_FAILURE !== '1', 'Requires controlled unavailable API')

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'mobile', width: 393, height: 852 },
  ]) {
    test(`${viewport.name} keeps an unavailable Watchlist explicit`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/watchlist')

      await expect(page.getByRole('alert', { name: 'Watchlist unavailable' })).toBeVisible()
      await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
      await expect(page.getByText(/Frozen synthetic/i)).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Update latest data' })).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    })
  }
})
