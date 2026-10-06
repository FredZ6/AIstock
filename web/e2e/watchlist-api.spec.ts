import { expect, test } from '@playwright/test'

const apiBaseUrl = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000'
const expectApiFailure = process.env.EXPECT_API_FAILURE === '1'
const testSymbol = 'QAWEBAPI'

async function deleteTestSymbol() {
  const response = await fetch(`${apiBaseUrl}/api/v1/watchlist/${testSymbol}`, {
    method: 'DELETE',
  })
  expect([204, 404]).toContain(response.status)
}

test.beforeEach(async ({ page }) => {
  await page.route(/tradingview\.com/, (route) => route.abort())
})

test('persists Watchlist configuration through FastAPI and PostgreSQL', async ({ page }) => {
  test.skip(expectApiFailure, 'Controlled failure run')
  await deleteTestSymbol()

  try {
    await page.goto('/watchlist')
    await expect(page.getByText('Discover · API Mode')).toBeVisible()
    await expect(page.getByText('Fixture Mode')).toHaveCount(0)

    await page.getByRole('textbox', { name: 'Add symbol' }).fill(testSymbol)
    await page.getByRole('button', { name: 'Add to watchlist' }).click()
    await expect(page.getByRole('link', { name: testSymbol })).toBeVisible()
    const settings = page.getByRole('region', { name: `${testSymbol} settings` })
    await settings.getByText(`${testSymbol} settings`, { exact: true }).click()

    await settings.getByRole('checkbox', { name: `${testSymbol} intraday monitoring` }).uncheck()
    await settings.getByRole('textbox', { name: `${testSymbol} alert threshold` }).fill('0.031')
    await settings.getByRole('button', { name: `Save ${testSymbol} settings` }).click()
    await expect(settings.getByRole('status')).toContainText(`${testSymbol} updated.`)

    await page.reload()
    const persistedSettings = page.getByRole('region', { name: `${testSymbol} settings` })
    await persistedSettings.getByText(`${testSymbol} settings`, { exact: true }).click()
    await expect(persistedSettings.getByRole('checkbox', {
      name: `${testSymbol} intraday monitoring`,
    })).not.toBeChecked()
    await expect(persistedSettings.getByRole('textbox', {
      name: `${testSymbol} alert threshold`,
    })).toHaveValue('0.031')

    const deleteTrigger = persistedSettings.getByRole('button', { name: `Delete ${testSymbol}` })
    await deleteTrigger.click()
    const confirmation = page.getByRole('alertdialog', { name: `Remove ${testSymbol} from watchlist?` })
    await expect(confirmation).toContainText(`This removes ${testSymbol} monitoring settings`)
    await page.keyboard.press('Escape')
    await expect(confirmation).toHaveCount(0)
    await expect(deleteTrigger).toBeFocused()
    await expect(persistedSettings.getByRole('textbox', {
      name: `${testSymbol} alert threshold`,
    })).toHaveValue('0.031')

    await deleteTrigger.click()
    await page.getByRole('button', { name: `Confirm remove ${testSymbol}` }).click()
    await expect(page.getByRole('link', { name: testSymbol })).toHaveCount(0)
  } finally {
    await deleteTestSymbol()
  }
})

test('shows Failure without Fixture substitution when FastAPI is unavailable', async ({ page }) => {
  test.skip(!expectApiFailure, 'Persisted API run')

  await page.goto('/watchlist')

  await expect(page.getByRole('alert', { name: 'Watchlist unavailable' })).toBeVisible()
  await expect(page.getByText('Fixture Mode')).toHaveCount(0)
  await expect(page.getByText(/fixture-market/i)).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Ranked research watchlist' })).toHaveCount(0)
})

test.describe('manual Watchlist refresh admission', () => {
  test.skip(process.env.RUN_API_BROWSER !== '1', 'Requires isolated API browser harness')

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'mobile', width: 393, height: 852 },
  ]) {
    test(`${viewport.name} exposes a focused, truthful refresh flow`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/watchlist')

      const summary = page.getByRole('region', { name: 'Watchlist critical summary' })
      const refresh = summary.getByRole('button', { name: 'Update latest data' })
      await expect(refresh).toBeVisible()
      await refresh.focus()
      await expect.poll(() => refresh.evaluate((element) => {
        const style = getComputedStyle(element)
        return style.outlineStyle !== 'none' && style.outlineWidth !== '0px'
      })).toBe(true)

      const persistedTimes = await summary.locator('time').allTextContents()
      await refresh.click()

      const status = summary.getByRole('status').or(summary.getByRole('alert'))
      await expect(status).toBeVisible()
      await expect(status).not.toContainText(/prices? (?:are|were) updated/i)
      await expect(status).toContainText(/(?:queued|already processing|paper mode|unavailable|try again)/i)
      await expect(summary).not.toContainText('Fixture Mode')

      // The current test harness deliberately uses environment=test and therefore
      // reports PAPER_MODE_REQUIRED. A paper harness can opt into the admitted
      // response without changing this deterministic browser contract.
      if (process.env.EXPECT_REFRESH_QUEUED === '1') {
        await expect(status).toContainText(/queued|already processing/i)
        await expect(status).toContainText(/newly persisted prices after ingestion completes/i)
      }
      for (const timestamp of persistedTimes) {
        if (timestamp.trim()) await expect(summary).toContainText(timestamp)
      }
    })
  }
})
