import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

test.describe('FRE-43 persisted production loop', () => {
  test.skip(
    process.env.RUN_PRODUCTION_LOOP_E2E !== '1',
    'requires the managed paper runtime and persisted production-loop facts',
  )

  async function expectSafeApiPage(page: Page) {
    await expect(page.getByText(/Fixture Mode/i)).toHaveCount(0)
    await expect(page.getByText(/Frozen synthetic/i)).toHaveCount(0)
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(await page.evaluate(() => document.documentElement.clientWidth))
    const accessibility = await new AxeBuilder({ page }).analyze()
    expect(
      accessibility.violations.filter(
        (violation) => violation.impact === 'serious' || violation.impact === 'critical',
      ),
    ).toEqual([])
  }

  test('renders durable research, paper-only risk, alerts, and learning evidence', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/watchlist')
    const watchlist = page.getByRole('list', { name: 'Ranked research watchlist' })
    await expect(watchlist).toBeVisible()
    await expect(watchlist.getByRole('link', { name: 'NVDA', exact: true })).toBeVisible()
    await expect(page.getByText(/Research unavailable/i)).toHaveCount(0)
    await expectSafeApiPage(page)

    await page.goto('/portfolio')
    await expect(page.getByRole('region', { name: 'Portfolio snapshot' })).toContainText('USD 100,000.00')
    const risk = page.getByRole('table', { name: 'Risk decisions' })
    await expect(risk).toContainText('REJECTED')
    await expect(risk).toContainText('MARKET_DATA_ENTITLEMENT')
    await expect(page.getByRole('table', { name: 'Paper fills' })).toHaveCount(0)
    await expectSafeApiPage(page)

    await page.goto('/alerts')
    const alerts = page.getByRole('list', { name: 'Persisted alerts' })
    const empty = page.getByRole('status', { name: 'No persisted alerts' })
    const persisted = alerts.getByRole('listitem')
    if (await persisted.count() === 0) {
      await expect(empty).toContainText('monitoring thresholds')
    } else {
      await expect(persisted.first()).toBeVisible()
      const keys = await persisted.evaluateAll((items) => items.map((item) => {
        const labels = [...item.querySelectorAll('dt')]
        const label = labels.find((candidate) => candidate.textContent === 'Alert key')
        return label?.parentElement?.querySelector('code')?.textContent ?? ''
      }))
      expect(keys.every(Boolean)).toBe(true)
      expect(new Set(keys).size).toBe(keys.length)
    }
    await expectSafeApiPage(page)

    await page.goto('/weekly-review')
    const outcomes = page.getByRole('table', { name: 'Persisted weekly outcomes' })
    await expect(outcomes).toBeVisible()
    await expect(outcomes.locator('tbody tr')).not.toHaveCount(0)
    await expect(outcomes.getByText('Benchmark comparison (excess)', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Confidence calibration' })).toBeVisible()
    await expectSafeApiPage(page)
  })
})
