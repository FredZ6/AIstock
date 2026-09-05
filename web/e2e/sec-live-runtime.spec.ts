import { expect, test } from '@playwright/test'

test('API-mode research renders persisted SEC facts without Fixture fallback', async ({ page }) => {
  test.skip(process.env.RUN_SEC_LIVE_BROWSER !== '1', 'Requires local persisted SEC facts')
  await page.goto('/research/NVDA')
  await expect(page.getByRole('heading', { name: 'SEC filings' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Financial facts' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'SEC data quality' })).toBeVisible()
  await expect(page.getByText('0001045810-26-000075').first()).toBeVisible()
  await expect(page.getByText('live/SEC/filing_sections/', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('FRESHNESS').first()).toBeVisible()
  await expect(page.getByText('PASS').first()).toBeVisible()
  await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>('body *')]
      .map((element) => ({
        className: element.className,
        right: Math.ceil(element.getBoundingClientRect().right),
        tag: element.tagName,
      }))
      .filter((element) => element.right > window.innerWidth + 1)
      .slice(0, 10),
    viewportWidth: window.innerWidth,
  }))
  expect(overflow, JSON.stringify(overflow)).toMatchObject({ documentWidth: overflow.viewportWidth })
})
