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
  ['/watchlist', '.watchlist-critical-summary'],
  ['/research/NVDA', '.research-critical-summary'],
  ['/runs/latest', '.run-overview'],
  ['/portfolio', '.portfolio-critical-summary'],
  ['/alerts', '.alert-triage-summary'],
  ['/weekly-review', '.weekly-outcome-summary'],
  ['/eval', '.operational-evidence'],
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

async function focusWithKeyboard(
  page: import('@playwright/test').Page,
  target: import('@playwright/test').Locator,
) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
  })
  for (let index = 0; index < 32; index += 1) {
    await page.keyboard.press('Tab')
    if (await target.evaluate((element) => document.activeElement === element)) return
  }
  throw new Error('Target was not reachable with keyboard Tab navigation')
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

test('the five-symbol watchlist and its critical controls fit the 13-inch desktop fold', async ({ page }) => {
  await page.setViewportSize({ height: 800, width: 1440 })
  await page.goto('/watchlist')

  await expect(page.getByRole('list', { name: 'Ranked research watchlist' }).getByRole('listitem')).toHaveCount(5)
  const marketChart = page.getByRole('group', { name: 'External current market chart' })
  await expect(marketChart).toBeVisible()
  const bottom = await marketChart.evaluate((element) => element.getBoundingClientRect().bottom)
  expect(bottom).toBeLessThanOrEqual(800)
})

test('dense Today links retain a 44px pointer target', async ({ page }) => {
  await page.setViewportSize({ height: 800, width: 1440 })
  await page.goto('/')

  const links = [
    page.locator('.today-watchlist').getByRole('link', { name: 'NVDA', exact: true }),
    page.locator('.today-watchlist').getByRole('link', { name: 'MSFT', exact: true }),
    page.locator('.research-activity').getByRole('link', { name: 'Daily research · NVDA' }),
  ]
  for (const link of links) {
    const bounds = await link.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.height).toBeGreaterThanOrEqual(44)
  }
})

test('all product routes remain readable across the locked viewport matrix', async ({ page }) => {
  test.slow()
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
  const viewport = { width: 1440, height: 800 }
  await page.setViewportSize(viewport)
  for (const [path, selector] of criticalTargets) {
    await page.goto(path)
    const target = page.locator(selector).first()
    await expect(target, `${path} critical target missing at ${viewport.width}x${viewport.height}`).toBeVisible()
    const bounds = await target.boundingBox()
    expect(bounds, `${path} critical target has no bounds`).not.toBeNull()
    expect(
      bounds!.y + bounds!.height,
      `${path} critical summary extends below the first viewport at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(viewport.height)

    const undersizedText = await page.locator('main').evaluate((main) => Array.from(main.querySelectorAll<HTMLElement>('*')).flatMap((element) => {
      const directText = Array.from(element.childNodes)
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent?.trim() ?? '')
        .join(' ')
        .trim()
      const closedDisclosure = element.closest('details:not([open])')
      if (closedDisclosure && !element.closest('summary')) return []
      if (!directText || element.closest('[hidden], .sr-only') || element.getClientRects().length === 0 || getComputedStyle(element).display === 'none') return []
      const size = Number.parseFloat(getComputedStyle(element).fontSize)
      return size < 13 ? [`${element.tagName.toLowerCase()}.${element.className || '(no-class)'}=${size}px:${directText.slice(0, 40)}`] : []
    }))
    expect(undersizedText, `${path} must keep visible body and data text at or above 13px`).toEqual([])
  }
})

test('Today uses the approved split workspace without overlapping facts', async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 800 }, { width: 1280, height: 720 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/')

    const workspace = page.getByRole('region', { name: 'Today decision workspace' })
    const summary = page.getByRole('region', { name: 'Market and portfolio summary' })
    const regime = summary.getByRole('region', { name: 'Market regime' })
    const regimeMetrics = regime.locator('.metric-list')
    const benchmarkPulse = regime.locator('.benchmark-pulse')
    const watchlist = page.locator('.today-watchlist')
    const activity = page.getByRole('region', { name: 'Decision activity' })
    const [workspaceBounds, summaryBounds, watchlistBounds, activityBounds, regimeBounds, regimeMetricsBounds, benchmarkPulseBounds] = await Promise.all([
      workspace.boundingBox(),
      summary.boundingBox(),
      watchlist.boundingBox(),
      activity.boundingBox(),
      regime.boundingBox(),
      regimeMetrics.boundingBox(),
      benchmarkPulse.boundingBox(),
    ])

    expect(workspaceBounds).not.toBeNull()
    expect(summaryBounds).not.toBeNull()
    expect(watchlistBounds).not.toBeNull()
    expect(activityBounds).not.toBeNull()
    expect(regimeBounds).not.toBeNull()
    expect(regimeMetricsBounds).not.toBeNull()
    expect(benchmarkPulseBounds).not.toBeNull()
    expect(summaryBounds!.x, `summary was not in the left column at ${viewport.width}x${viewport.height}`)
      .toBeLessThan(watchlistBounds!.x)
    expect(
      Math.abs(watchlistBounds!.x - activityBounds!.x),
      `watchlist and decision activity did not share the right column at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(2)
    expect(watchlistBounds!.y, `watchlist was not above decision activity at ${viewport.width}x${viewport.height}`)
      .toBeLessThan(activityBounds!.y)
    expect(
      Math.abs(summaryBounds!.y + summaryBounds!.height - (activityBounds!.y + activityBounds!.height)),
      `decision activity did not align with the portfolio bottom at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(2)
    const horizontalGap = watchlistBounds!.x - (summaryBounds!.x + summaryBounds!.width)
    const verticalGap = activityBounds!.y - (watchlistBounds!.y + watchlistBounds!.height)
    expect(
      Math.abs(horizontalGap - verticalGap),
      `Today surface gaps were inconsistent at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(2)
    expect(
      workspaceBounds!.y + workspaceBounds!.height,
      `Today workspace exceeded the first viewport at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(viewport.height)
    expect(
      benchmarkPulseBounds!.y,
      `Benchmark pulse overlapped regime metrics at ${viewport.width}x${viewport.height}`,
    ).toBeGreaterThanOrEqual(regimeMetricsBounds!.y + regimeMetricsBounds!.height)
    expect(
      benchmarkPulseBounds!.y + benchmarkPulseBounds!.height,
      `Benchmark pulse escaped Market regime at ${viewport.width}x${viewport.height}`,
    ).toBeLessThanOrEqual(regimeBounds!.y + regimeBounds!.height + 1)

    const firstCard = watchlist.locator('.watchlist-heatmap > li').first()
    const factBounds = await firstCard.locator(':scope > .heatmap-primary, :scope > span, :scope > .heatmap-decisions, :scope > .quality-line')
      .evaluateAll((elements) => elements.map((element) => {
        const bounds = element.getBoundingClientRect()
        return { bottom: bounds.bottom, left: bounds.left, right: bounds.right, top: bounds.top }
      }))
    for (let leftIndex = 0; leftIndex < factBounds.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < factBounds.length; rightIndex += 1) {
        const left = factBounds[leftIndex]
        const right = factBounds[rightIndex]
        const separated = left.bottom <= right.top + 1 || right.bottom <= left.top + 1 || left.right <= right.left + 1 || right.right <= left.left + 1
        expect(separated, `watchlist facts overlapped at ${viewport.width}x${viewport.height}`).toBe(true)
      }
    }

    await expect(activity.locator('.alert-list > li').last()).toHaveCSS('border-bottom-width', '0px')
    await expect(summary.locator('.performance-overview.is-compact .chart-dates')).toHaveCSS('border-top-width', '0px')
  }
})

test('Today watchlist disclosure preserves native keyboard focus across the viewport matrix', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 800 },
    { width: 1280, height: 720 },
    { width: 393, height: 852 },
  ]) {
    await page.setViewportSize(viewport)
    await page.goto('/')

    const workspace = page.getByRole('region', { name: 'Today decision workspace' })
    const watchlist = workspace.getByRole('region', { name: 'Watchlist signals' })
    const list = watchlist.getByRole('list', { name: 'Watchlist signals' })
    const listId = await list.getAttribute('id')
    const showAll = watchlist.getByRole('button', { name: 'Show all (5)' })

    expect(listId).toBeTruthy()
    await expect(list.getByRole('listitem')).toHaveCount(2)
    await expect(showAll).toHaveAttribute('aria-expanded', 'false')
    await expect(showAll).toHaveAttribute('aria-controls', listId!)

    if (viewport.width >= 1280) {
      const workspaceBounds = await workspace.boundingBox()
      expect(workspaceBounds).not.toBeNull()
      expect(
        workspaceBounds!.y + workspaceBounds!.height,
        `collapsed Today workspace exceeded ${viewport.width}x${viewport.height}`,
      ).toBeLessThanOrEqual(viewport.height)
    }

    await focusWithKeyboard(page, showAll)
    await expect(showAll).toBeFocused()
    await page.keyboard.press('Enter')

    const showLess = watchlist.getByRole('button', { name: 'Show less' })
    await expect(showLess).toHaveAttribute('aria-expanded', 'true')
    await expect(showLess).toHaveAttribute('aria-controls', listId!)
    await expect(showLess).toBeFocused()
    await expect(list).toHaveAttribute('id', listId!)
    await expect(list.getByRole('listitem')).toHaveCount(5)

    await page.keyboard.press('Space')
    await expect(showAll).toHaveAttribute('aria-expanded', 'false')
    await expect(showAll).toBeFocused()
    await expect(list).toHaveAttribute('id', listId!)
    await expect(list.getByRole('listitem')).toHaveCount(2)

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
})

test('Today portfolio tabs control one chart and remain readable in both themes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 800 })
  await page.goto('/')

  const figure = page.getByRole('figure', { name: 'Paper portfolio performance' })
  const plot = figure.getByRole('tabpanel')
  const tabs = figure.getByRole('tablist', { name: 'Performance metric' })
  const nav = tabs.getByRole('tab', { name: 'Net asset value' })
  const dayReturn = tabs.getByRole('tab', { name: 'Day return' })
  const drawdown = tabs.getByRole('tab', { name: 'Current drawdown' })

  await expect(figure.getByRole('img', { name: 'Net asset value history' })).toBeVisible()
  await expect(plot).toHaveAttribute('data-metric', 'nav')
  await expect(plot.locator('svg')).toHaveCount(1)

  await focusWithKeyboard(page, nav)
  await page.keyboard.press('ArrowRight')
  await expect(dayReturn).toBeFocused()
  await expect(dayReturn).toHaveAttribute('aria-selected', 'true')
  await expect(plot).toHaveAttribute('data-metric', 'dailyReturn')
  await expect(figure.getByRole('img', { name: 'Day return history' })).toBeVisible()
  await expect(plot.locator('svg')).toHaveCount(1)

  await drawdown.click()
  await expect(drawdown).toHaveAttribute('aria-selected', 'true')
  await expect(plot).toHaveAttribute('data-metric', 'drawdown')
  await expect(figure.getByRole('img', { name: 'Current drawdown history' })).toBeVisible()
  await expect(plot.locator('svg')).toHaveCount(1)

  for (const theme of ['light', 'dark'] as const) {
    if (await page.locator('html').getAttribute('data-theme') !== theme) {
      await page.getByRole('button', { name: `Switch to ${theme} mode` }).click()
    }
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    await focusWithKeyboard(page, drawdown)
    await expect(drawdown).toBeFocused()
    await expect(drawdown).toHaveCSS('outline-style', 'solid')
    await expect(figure.getByRole('img', { name: 'Current drawdown history' })).toBeVisible()
    const colors = await drawdown.evaluate((element) => {
      const style = getComputedStyle(element)
      return { background: style.backgroundColor, foreground: style.color }
    })
    expect(colors.foreground).not.toBe(colors.background)
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
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
