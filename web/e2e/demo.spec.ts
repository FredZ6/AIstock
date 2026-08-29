import { mkdir } from 'node:fs/promises'
import path from 'node:path'

import { expect, test } from '@playwright/test'

const screenshotDirectory = process.env.DEMO_REPORT_DIR
  ? path.resolve(process.env.DEMO_REPORT_DIR, 'screenshots')
  : path.resolve('..', 'evals', 'reports', 'latest', 'screenshots')

test.beforeEach(async ({ page }) => {
  await page.route(/tradingview\.com/, (route) => route.abort())
})

test('the ten-minute fixture demo exposes every interview acceptance artifact', async ({ page }, testInfo) => {
  const projectScreenshotDirectory = testInfo.project.name === 'desktop-chrome'
    ? screenshotDirectory
    : path.join(screenshotDirectory, testInfo.project.name)
  await mkdir(projectScreenshotDirectory, { recursive: true })

  await page.goto('/research/NVDA')
  await expect(page.getByRole('heading', { level: 1, name: 'NVDA research' })).toBeVisible()
  await expect(page.getByText('CONFLICTED', { exact: true })).toBeVisible()
  await page.screenshot({ fullPage: true, path: path.join(projectScreenshotDirectory, '01-research.png') })

  await page.goto('/alerts')
  await expect(page.getByRole('button', { name: 'Acknowledge alert alert-nvda-volume-001' })).toBeVisible()
  await expect(page.getByText('Relative volume and return z-score crossed the frozen deterministic rule.')).toBeVisible()

  await page.goto('/portfolio')
  await expect(page.getByText('USD 100,425.18', { exact: true })).toBeVisible()
  await expect(page.getByText('-1.80%', { exact: true })).toBeVisible()
  await expect(page.getByRole('rowheader', { name: 'risk-decision-001' })).toBeVisible()
  await expect(page.getByText('REJECTED', { exact: true })).toBeVisible()
  await expect(page.getByRole('rowheader', { name: 'fill-nvda-001' })).toBeVisible()
  for (const benchmark of ['Cash', 'QQQ', 'Equal weight', 'Momentum']) {
    await expect(page.getByText(benchmark, { exact: true })).toBeVisible()
  }
  await page.getByRole('tab', { name: 'Drawdown' }).click()
  await expect(page.getByRole('img', { name: 'Drawdown history' })).toBeVisible()
  await page.screenshot({ fullPage: true, path: path.join(projectScreenshotDirectory, '02-portfolio.png') })

  await page.goto('/weekly-review')
  await expect(page.getByRole('heading', { level: 2, name: 'lesson-risk-regime-001' })).toBeVisible()
  await expect(page.getByText('APPROVED', { exact: true })).toBeVisible()
  await expect(page.getByText(/Unapproved activation rejected/)).toBeVisible()
  await page.screenshot({ fullPage: true, path: path.join(projectScreenshotDirectory, '03-weekly-review.png') })

  await page.goto('/eval')
  await expect(page.getByRole('heading', { level: 2, name: 'Offline evaluation report' })).toBeVisible()
  await expect(page.getByText('eval-v0.2.0', { exact: true })).toBeVisible()
  await expect(page.getByText('200 cases', { exact: true })).toBeVisible()
  await expect(page.getByText('PASS', { exact: true })).toBeVisible()
  await page.screenshot({ fullPage: true, path: path.join(projectScreenshotDirectory, '04-eval.png') })
})
