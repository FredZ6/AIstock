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
    await expect(page.getByRole('status', { name: 'Market and research data unavailable' })).toBeVisible()
    await expect(page.getByText('Fixture Mode')).toHaveCount(0)

    await page.getByRole('textbox', { name: 'Add symbol' }).fill(testSymbol)
    await page.getByRole('button', { name: 'Add to watchlist' }).click()
    const row = page.getByRole('row').filter({ has: page.getByRole('rowheader', { name: testSymbol }) })
    await expect(row).toBeVisible()

    await row.getByRole('checkbox', { name: `${testSymbol} intraday monitoring` }).uncheck()
    await row.getByRole('textbox', { name: `${testSymbol} alert threshold` }).fill('0.031')
    await row.getByRole('button', { name: `Save ${testSymbol} settings` }).click()
    await expect(row.getByRole('status')).toContainText(`${testSymbol} updated.`)

    await page.reload()
    const persistedRow = page.getByRole('row').filter({
      has: page.getByRole('rowheader', { name: testSymbol }),
    })
    await expect(persistedRow.getByRole('checkbox', {
      name: `${testSymbol} intraday monitoring`,
    })).not.toBeChecked()
    await expect(persistedRow.getByRole('textbox', {
      name: `${testSymbol} alert threshold`,
    })).toHaveValue('0.031')

    await persistedRow.getByRole('button', { name: `Delete ${testSymbol}` }).click()
    await expect(page.getByRole('rowheader', { name: testSymbol })).toHaveCount(0)
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
  await expect(page.getByRole('table', { name: 'Research watchlist' })).toHaveCount(0)
})
