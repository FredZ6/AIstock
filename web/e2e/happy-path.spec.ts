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

const criticalTargets = [
  ['/', '.today-decision-workspace'],
  ['/watchlist', '.route-critical-summary'],
  ['/research/NVDA', '.research-critical-summary'],
  ['/runs/latest', '.run-overview'],
  ['/portfolio', '.portfolio-critical-summary'],
  ['/alerts', '.alert-cards > li:first-child'],
  ['/weekly-review', '.outcome-strip'],
  ['/eval', '.operations-status-grid'],
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
  await page.getByRole('group', { name: 'Complete durable event trace' }).locator('summary').click()
  await expect(page.getByRole('list', { name: 'Durable run events' })).toBeVisible()
  await expect(page.getByText(/Last-Event-ID/)).toBeVisible()
})

test('keyboard focus is visible and the document does not overflow its viewport', async ({ page }) => {
  await page.goto('/watchlist', { waitUntil: 'networkidle' })
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

test('decision-critical content lands inside the MacBook Air first viewport', async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 800 }, { width: 1280, height: 720 }]) {
    await page.setViewportSize(viewport)
    for (const [path, selector] of criticalTargets) {
      await page.goto(path)
      const target = page.locator(selector).first()
      await expect(target, `${path} critical target missing at ${viewport.width}x${viewport.height}`).toBeVisible()
      const bounds = await target.boundingBox()
      expect(bounds, `${path} critical target has no bounds`).not.toBeNull()
      expect(bounds!.y, `${path} critical target begins below the first viewport at ${viewport.width}x${viewport.height}`).toBeLessThan(viewport.height)
      expect(
        Math.min(bounds!.y + bounds!.height, viewport.height),
        `${path} exposes too little critical content at ${viewport.width}x${viewport.height}`,
      ).toBeGreaterThanOrEqual(bounds!.y + Math.min(88, bounds!.height))
    }
  }
})

test('Today uses the approved split workspace without overlapping facts', async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 800 }, { width: 1280, height: 720 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/')

    const workspace = page.getByRole('region', { name: 'Today decision workspace' })
    const summary = page.getByRole('region', { name: 'Market and portfolio summary' })
    const watchlist = page.locator('.today-watchlist')
    const activity = page.getByRole('region', { name: 'Decision activity' })
    const [workspaceBounds, summaryBounds, watchlistBounds, activityBounds] = await Promise.all([
      workspace.boundingBox(),
      summary.boundingBox(),
      watchlist.boundingBox(),
      activity.boundingBox(),
    ])

    expect(workspaceBounds).not.toBeNull()
    expect(summaryBounds).not.toBeNull()
    expect(watchlistBounds).not.toBeNull()
    expect(activityBounds).not.toBeNull()
    expect(summaryBounds!.x, `summary was not in the left column at ${viewport.width}x${viewport.height}`)
      .toBeLessThan(watchlistBounds!.x)
    expect(
      Math.abs(watchlistBounds!.x - activityBounds!.x),
      `watchlist and decision activity did not share the right column at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(2)
    expect(watchlistBounds!.y, `watchlist was not above decision activity at ${viewport.width}x${viewport.height}`)
      .toBeLessThan(activityBounds!.y)
    expect(
      workspaceBounds!.y + workspaceBounds!.height,
      `Today workspace exceeded the first viewport at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(viewport.height)

    const firstCard = watchlist.locator('.watchlist-heatmap > li').first()
    const verticalFacts = await firstCard.locator(':scope > .heatmap-primary, :scope > span, :scope > .heatmap-decisions, :scope > .quality-line')
      .evaluateAll((elements) => elements.map((element) => {
        const bounds = element.getBoundingClientRect()
        return { bottom: bounds.bottom, top: bounds.top }
      }))
    for (let index = 1; index < verticalFacts.length; index += 1) {
      expect(
        verticalFacts[index].top,
        `watchlist facts overlapped at ${viewport.width}x${viewport.height}`,
      ).toBeGreaterThanOrEqual(verticalFacts[index - 1].bottom - 1)
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

test('a blocked TradingView embed retains an accessible current-market fallback', async ({ page }) => {
  await page.goto('/research/NVDA')
  await page.getByRole('group', { name: 'Current market reference' }).locator('summary').click()
  const widget = page.getByRole('region', { name: 'NVDA current market overview' })
  await widget.scrollIntoViewIfNeeded()

  await expect(widget.getByRole('status', { name: 'Current market reference unavailable' }))
    .toContainText('TradingView could not be loaded')
  await expect(widget.getByRole('link', { name: 'Open NVDA on TradingView' }))
    .toHaveAttribute('href', 'https://www.tradingview.com/symbols/NVDA/')
  await expect(widget).toContainText('Not decision-time evidence')

  await page.goto('/portfolio')
  await page.getByRole('group', { name: 'Complete positions' }).locator('summary').click()
  const miniChart = page.locator('section.market-widget-mini-chart').first()
  await miniChart.scrollIntoViewIfNeeded()
  await expect(miniChart.getByRole('status', { name: 'Current market reference unavailable' }))
    .toBeVisible()
})

test('core workflows reflow at 200% text zoom without page-level horizontal scrolling', async ({ page }) => {
  await page.setViewportSize({ height: 900, width: 768 })

  for (const [path, heading] of pages) {
    await page.goto(path)
    await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    const layout = await inspectHorizontalOverflow(page)
    expect(layout.fits, `${path} overflowed at 200% text zoom: ${JSON.stringify(layout)}`).toBe(true)
  }
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
