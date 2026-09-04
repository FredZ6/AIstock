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
