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
