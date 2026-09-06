import { expect, test } from '@playwright/test'

const pages = [
  ['/', 'Today'],
  ['/watchlist', 'Watchlist'],
  ['/research/NVDA', 'NVDA research'],
  ['/runs/latest', 'Research run · NVDA'],
  ['/portfolio', 'AI Portfolio'],
  ['/alerts', 'Alerts'],
  ['/weekly-review', 'Weekly Review'],
  ['/eval', 'Eval & Admin'],
] as const

test.beforeEach(async ({ page }) => {
  await page.route(/tradingview\.com/, (route) => route.abort())
})

test('all eight product pages preserve navigation, safety copy, and one clear heading', async ({ page }) => {
  for (const [path, heading] of pages) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible()
    const footer = page.getByRole('contentinfo')
    await expect(footer.getByText(/Paper Trading only/i)).toBeVisible()
    await expect(footer.getByText(/Not investment advice/i)).toBeVisible()
    await expect(page.locator('h1')).toHaveCount(1)
  }
})

test('a reviewer traces a Today conclusion through report, evidence, provider, ToolCall, and run event', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'NVDA' }).first().click()

  await expect(page).toHaveURL(/\/research\/NVDA$/)
  await expect(page.getByText('report-nvda-v3')).toBeVisible()
  await expect(page.getByText('claim-nvda-demand')).toBeVisible()
  await expect(page.getByText('evidence-sec-revenue')).toBeVisible()
  await expect(page.getByText('tool-sec-companyfacts')).toBeVisible()
  await expect(page.getByText(/SEC Company Facts/)).toBeVisible()
  await expect(page.getByText(/New York/).first()).toBeVisible()

  await page.getByRole('link', { name: 'Open run trace' }).click()
  await expect(page).toHaveURL(/\/runs\/latest$/)
  await expect(page.getByRole('list', { name: 'Durable run events' })).toBeVisible()
  await expect(page.getByText(/Last-Event-ID/)).toBeVisible()
})

test('keyboard focus is visible and the document does not overflow its viewport', async ({ page }) => {
  await page.goto('/watchlist')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused()
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toHaveCSS('outline-style', 'solid')

  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflows).toBe(false)
})

test('compact layouts expose every destination through an explicit navigation menu', async ({ page }) => {
  await page.setViewportSize({ height: 852, width: 393 })
  await page.goto('/')

  const navigation = page.getByRole('navigation', { name: 'Primary' })
  const trigger = page.getByRole('button', { name: 'Open navigation' })

  await expect(trigger).toBeVisible()
  await expect(navigation).toBeHidden()

  await trigger.click()

  await expect(page.getByRole('button', { name: 'Close navigation' })).toHaveAttribute(
    'aria-expanded',
    'true',
  )
  await expect(navigation).toBeVisible()
  await expect(navigation.getByRole('link')).toHaveCount(8)

  await page.keyboard.press('Escape')
  await expect(navigation).toBeHidden()

  for (const width of [320, 720]) {
    await page.setViewportSize({ height: 852, width })
    await page.reload()
    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    )
    expect(overflows, `${width}px layout overflowed`).toBe(false)
  }
})
