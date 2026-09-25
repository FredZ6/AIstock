import { expect, test } from '@playwright/test'

test('mobile Today summary stacks every critical region without internal clipping', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 })
  await page.goto('/')

  const summary = page.getByRole('region', { name: 'Market and portfolio summary' })
  const portfolio = summary.getByRole('region', { name: 'Portfolio overview' })
  const regime = summary.getByRole('region', { name: 'Market regime' })
  const [summaryBounds, portfolioBounds, regimeBounds] = await Promise.all([
    summary.boundingBox(),
    portfolio.boundingBox(),
    regime.boundingBox(),
  ])

  expect(summaryBounds).not.toBeNull()
  expect(portfolioBounds).not.toBeNull()
  expect(regimeBounds).not.toBeNull()
  expect(portfolioBounds!.y + portfolioBounds!.height).toBeLessThanOrEqual(regimeBounds!.y + 1)
  for (const bounds of [portfolioBounds!, regimeBounds!]) {
    expect(bounds.x).toBeGreaterThanOrEqual(summaryBounds!.x - 1)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(summaryBounds!.x + summaryBounds!.width + 1)
  }
})

test('mobile Today brings portfolio facts into the upper half of the first viewport', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 })
  await page.goto('/')

  const portfolioBounds = await page.getByRole('region', { name: 'Portfolio overview' }).boundingBox()

  expect(portfolioBounds).not.toBeNull()
  expect(portfolioBounds!.y).toBeLessThanOrEqual(400)
  await expect(page.locator('.mobile-current')).toHaveCSS('display', 'none')
})

test('desktop Today keeps decision activity labels on one line', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.goto('/')

  const activity = page.getByRole('region', { name: 'Decision activity' })
  const lineCount = async (selector: string) => activity.locator(selector).evaluate((element) => {
    const range = document.createRange()
    range.selectNodeContents(element)
    return range.getClientRects().length
  })

  expect(await lineCount('#alerts-title')).toBe(1)
  expect(await lineCount('a[href="/alerts"]')).toBe(1)
})

test('desktop Today keeps the portfolio NAV on one rendered line', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 800 },
    { width: 1280, height: 720 },
  ]) {
    await page.setViewportSize(viewport)
    await page.goto('/')

    const nav = page
      .getByRole('region', { name: 'Portfolio overview' })
      .getByText('Net asset value')
      .locator('..')
      .locator('dd')
    const renderedLines = await nav.evaluate((element) => {
      const range = document.createRange()
      range.selectNodeContents(element)
      return range.getClientRects().length
    })

    expect(renderedLines, `${viewport.width}px NAV line count`).toBe(1)
  }
})
