import { expect, test } from '@playwright/test'

test.describe('live provider closure', () => {
  test.skip(
    process.env.RUN_LIVE_PROVIDER_E2E !== '1',
    'requires the managed paper runtime and persisted real-provider data',
  )

  test('keeps API mode fail-closed and renders SEC provenance without viewport overflow', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('DECISION WORKSPACE · API MODE')).toBeVisible()
    await expect(page.getByText(/Fixture Mode/i)).toHaveCount(0)
    await expect(
      page.getByText('Configure ALPHA_VANTAGE_API_KEY to ingest the earnings calendar.'),
    ).toBeVisible()
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(await page.evaluate(() => document.documentElement.clientWidth))

    await page.goto('/research/NVDA')
    await expect(page.getByText('RESEARCH · API MODE')).toBeVisible()
    await expect(page.getByText('No Fixture data was substituted.')).toBeVisible()
    const unavailable = page.getByRole('region', { name: 'Unavailable research domains' })
    await expect(unavailable).toContainText(
      'Unsupported until an authoritative provider, schema, and license are approved.',
    )
    await expect(unavailable).toContainText(
      'Unavailable because the locked architecture has no approved lawful read-only Options provider.',
    )

    await page.locator('summary', { hasText: 'SEC filings' }).click()
    const filings = page.getByRole('table', { name: 'Persisted SEC filings' })
    await expect(filings.locator('th', { hasText: 'Provider' })).toBeVisible()
    await expect(filings.locator('th', { hasText: 'Event time' })).toBeVisible()
    await expect(filings.locator('th', { hasText: 'Available' })).toBeVisible()
    await expect(filings).toContainText('live/SEC/filing_sections/')
    await expect(filings).toContainText(/[a-f0-9]{64}/)
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(await page.evaluate(() => document.documentElement.clientWidth))
  })
})
