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
