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

async function exposeNavigation(page: import('@playwright/test').Page) {
  const navigation = page.getByRole('navigation', { name: 'Primary' })
  if (!(await navigation.isVisible())) {
    await page.getByRole('button', { name: 'Open navigation' }).click()
  }
  await expect(navigation).toBeVisible()
  return navigation
}

async function inspectHorizontalOverflow(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    window.scrollTo(100, window.scrollY)
    const pageScrollLeft = window.scrollX
    window.scrollTo(0, window.scrollY)
    return {
      fits: pageScrollLeft === 0,
      pageScrollLeft,
    }
  })
}

test.beforeEach(async ({ page }) => {
  await page.route(/tradingview\.com/, (route) => route.abort())
})

test('all eight product pages preserve navigation, safety copy, and one clear heading', async ({ page }) => {
  for (const [path, heading] of pages) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    const navigation = await exposeNavigation(page)
    await expect(navigation.getByRole('link')).toHaveCount(8)
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
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
  const headerBottom = await page.locator('.app-chrome').evaluate((element) => element.getBoundingClientRect().bottom)
  const headingTop = await page.getByRole('heading', { level: 1 }).evaluate((element) => element.getBoundingClientRect().top)
  expect(headingTop).toBeGreaterThanOrEqual(headerBottom)

  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflows).toBe(false)
})

test('all product routes remain readable across the locked viewport matrix', async ({ page }) => {
  for (const width of [320, 393, 768, 1120, 1440]) {
    await page.setViewportSize({ height: 900, width })
    for (const [path, heading] of pages) {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
      const layout = await inspectHorizontalOverflow(page)
      expect(layout.fits, `${path} allowed page-level horizontal scrolling at ${width}px: ${JSON.stringify(layout)}`).toBe(true)
      await exposeNavigation(page)
      await page.keyboard.press('Escape')
    }
  }
})

test('theme and reduced-motion preferences preserve a calm readable surface', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  const theme = page.getByRole('button', { name: 'Switch to dark mode' })
  await theme.click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const transitionDurationSeconds = await page.locator('button').first().evaluate((element) => (
    Number.parseFloat(getComputedStyle(element).transitionDuration)
  ))
  expect(transitionDurationSeconds).toBeLessThanOrEqual(0.00001)
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
