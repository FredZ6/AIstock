import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test.describe('isolated real API runtime', () => {
  test.skip(process.env.RUN_API_BROWSER !== '1', 'Requires isolated database harness')
  test.describe.configure({ mode: 'serial' })
  let api: ChildProcess | undefined
  const apiPort = process.env.BROWSER_API_PORT ?? '8107'
  const base = `http://127.0.0.1:${apiPort}`

  async function start() {
    api = spawn('../.venv/bin/python', ['-m', 'uvicorn', 'browser_api:app', '--host', '127.0.0.1', '--port', apiPort], {
      env: { ...process.env, PYTHONPATH: '../backend/src:../backend/tests' }, stdio: 'ignore',
    })
    await expect.poll(async () => {
      if (api?.exitCode !== null) return -1
      try { return (await fetch(`${base}/api/v1/watchlist`)).status } catch { return 0 }
    }, { timeout: 15000 }).toBe(200)
  }

  async function stop() {
    if (api && api.exitCode === null) {
      const exited = once(api, 'exit')
      api.kill('SIGTERM')
      await exited
    }
    api = undefined
  }

  test.beforeAll(start)
  test.afterAll(stop)

  test('reads persisted configuration, recovers from outage, and never substitutes fixtures', async ({ page }) => {
    await page.goto('/watchlist')
    await expect(page.getByRole('list', { name: 'Ranked research watchlist' })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Ranked research watchlist' }).getByRole('link', { name: 'NVDA', exact: true })).toBeVisible()
    await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
    await stop()
    await page.reload()
    await expect(page.getByRole('alert', { name: 'Watchlist unavailable' })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Ranked research watchlist' })).toHaveCount(0)
    await start()
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('list', { name: 'Ranked research watchlist' })).toBeVisible()
    await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
  })

  test('all eight routes render API states without fixture content or horizontal overflow', async ({ page }) => {
    const ids = process.env.BROWSER_EVENT_IDS!.split(',')
    for (const path of ['/', '/watchlist', '/research/NVDA', `/runs/${process.env.BROWSER_RUN_ID}`, '/portfolio', '/alerts', '/weekly-review', '/eval']) {
      await page.goto(path)
      await expect(page.locator('h1')).toHaveCount(1)
      await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
      await expect(page.getByText(/Frozen synthetic/i)).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    }
    await page.goto('/alerts')
    await expect(page.getByRole('status', { name: 'No persisted alerts' })).toBeVisible()
    await page.goto(`/runs/${process.env.BROWSER_RUN_ID}`)
    await expect(page.getByRole('region', { name: 'Run operations summary' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Deterministic Research Workflow' })).toBeVisible()
    await page.getByRole('group', { name: 'Complete durable event trace' }).locator('summary').click()
    await expect(page.getByRole('list', { name: 'Durable run events' }).getByRole('listitem')).toHaveCount(ids.length)
    const accessibility = await new AxeBuilder({ page }).analyze()
    expect(accessibility.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')).toEqual([])
  })

  test('availability summaries remain truthful, keyboard-operable, and accessible', async ({ page }) => {
    await page.goto('/')
    const summary = page.getByRole('status', { name: 'Some decision facts are unavailable' })
    await expect(summary).toBeVisible()
    const disclosure = summary.locator('summary')
    await disclosure.focus()
    await disclosure.press('Enter')
    const factCount = await summary.locator('.state-fact').count()
    expect(factCount).toBeGreaterThan(0)
    await expect(disclosure).toHaveText(`${factCount} unavailable facts`)
    await expect(summary.getByText('UNCONFIGURED · SEC')).toBeVisible()
    const alphaVantage = summary.locator('.state-fact').filter({ hasText: 'ALPHA VANTAGE' })
    await expect(alphaVantage).toHaveAttribute('data-availability-state', 'UNCONFIGURED')
    await expect(alphaVantage.locator('.state-fact-label')).toHaveText(/ALPHA VANTAGE$/)
    await expect(alphaVantage.locator('.state-fact-reason')).toHaveText(
      'Configure ALPHA_VANTAGE_API_KEY to ingest the earnings calendar.',
    )
    await expect(summary.getByText('EMPTY · Portfolio NAV')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
    expect(accessibility.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical')).toEqual([])

    await page.goto('/eval')
    await expect(page.getByRole('status', { name: 'No persisted evaluation runs' })).toContainText(
      'operator-only offline evaluation persistence workflow',
    )
  })

  test('API Today preserves the approved compact split workspace', async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 800 }, { width: 1280, height: 720 }]) {
      await page.setViewportSize(viewport)
      await page.goto('/')
      const summary = page.getByRole('region', { name: 'Market and portfolio summary' })
      const watchlist = page.getByRole('region', { name: 'Watchlist signals' })
      const activity = page.getByRole('region', { name: 'Decision activity' })
      const workspace = page.getByRole('region', { name: 'Today decision workspace' })
      const [summaryBounds, watchlistBounds, activityBounds, workspaceBounds] = await Promise.all([
        summary.boundingBox(), watchlist.boundingBox(), activity.boundingBox(), workspace.boundingBox(),
      ])
      expect(summaryBounds).not.toBeNull()
      expect(watchlistBounds).not.toBeNull()
      expect(activityBounds).not.toBeNull()
      expect(workspaceBounds).not.toBeNull()
      expect(summaryBounds!.x).toBeLessThan(watchlistBounds!.x)
      expect(watchlistBounds!.y).toBeLessThan(activityBounds!.y)
      expect(Math.abs(summaryBounds!.y + summaryBounds!.height - (activityBounds!.y + activityBounds!.height))).toBeLessThanOrEqual(2)
      const horizontalGap = watchlistBounds!.x - (summaryBounds!.x + summaryBounds!.width)
      const verticalGap = activityBounds!.y - (watchlistBounds!.y + watchlistBounds!.height)
      expect(Math.abs(horizontalGap - verticalGap)).toBeLessThanOrEqual(2)
      expect(workspaceBounds!.y + workspaceBounds!.height).toBeLessThanOrEqual(viewport.height)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    }

    await page.setViewportSize({ width: 393, height: 852 })
    await page.goto('/')
    const orderedRegions = await page.locator('.today-decision-workspace > .market-portfolio-grid, .today-decision-workspace > .today-watchlist, .today-decision-workspace > .decision-activity').evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().top))
    expect(orderedRegions).toEqual([...orderedRegions].sort((left, right) => left - right))
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('API Today renders persisted Portfolio history, ranked Watchlist disclosure, and latest run', async ({ page, request }) => {
    await page.goto('/')

    await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
    await expect(page.getByText(/Frozen synthetic/i)).toHaveCount(0)
    const portfolio = page.getByRole('figure', { name: 'Paper portfolio performance' })
    await expect(portfolio.getByRole('img', { name: 'Net asset value history' })).toBeVisible()
    await portfolio.getByRole('tab', { name: 'Day return' }).click()
    await expect(portfolio.getByRole('img', { name: 'Day return history' })).toBeVisible()
    await portfolio.getByRole('tab', { name: 'Current drawdown' }).click()
    await expect(portfolio.getByRole('img', { name: 'Current drawdown history' })).toBeVisible()
    await expect(portfolio.getByText('Persisted paper NAV history')).toBeVisible()

    const watchlist = page.getByRole('list', { name: 'Watchlist signals' })
    await expect(watchlist.getByRole('listitem')).toHaveCount(2)
    await expect(watchlist.getByRole('listitem').nth(0).getByRole('link')).toHaveText('NVDA')
    await expect(watchlist.getByRole('listitem').nth(1).getByRole('link')).toHaveText('AVGO')
    const disclosure = page.getByRole('button', { name: 'Show all (11)' })
    await disclosure.focus()
    await disclosure.press('Enter')
    const collapse = page.getByRole('button', { name: 'Show less' })
    await expect(collapse).toHaveAttribute('aria-expanded', 'true')
    await expect(watchlist.getByRole('listitem')).toHaveCount(11)
    await expect(watchlist.getByRole('link')).toHaveText([
      'NVDA', 'AVGO', 'TSM', 'SKHY', 'WDC', 'SNDK', 'MU', 'NBIS', 'MRVL', 'BE', 'INTC',
    ])
    await collapse.press('Space')
    await expect(page.getByRole('button', { name: 'Show all (11)' })).toHaveAttribute('aria-expanded', 'false')
    await expect(watchlist.getByRole('listitem')).toHaveCount(2)
    await expect(watchlist.getByRole('link')).toHaveText(['NVDA', 'AVGO'])

    const decisionTime = new Date(Date.now() + 1000).toISOString()
    const latestResponse = await request.get(`${base}/api/v1/research-runs/latest?decision_time=${encodeURIComponent(decisionTime)}`)
    expect(latestResponse.status()).toBe(200)
    const latest = await latestResponse.json() as { run_id: string; status: string }
    const run = page.getByRole('region', { name: 'Research execution' })
    await expect(run.getByRole('link', { name: 'Research · NVDA' })).toHaveAttribute('href', `/runs/${latest.run_id}`)
    await expect(run).toContainText(latest.status)
  })

  test('duplicate API admissions return the same durable run', async ({ request }) => {
    const idempotencyKey = `browser-idempotency-${process.env.BROWSER_RUN_ID}`
    const payload = { symbol: 'NVDA', decision_time: '2026-08-16T00:00:00Z', data_cutoff: '2026-08-16T00:00:00Z' }
    const submit = () => request.post(`${base}/api/v1/research-runs`, {
      data: payload,
      headers: { 'Idempotency-Key': idempotencyKey },
    })
    const first = await submit()
    const second = await submit()
    expect(first.status()).toBe(202)
    expect(second.status()).toBe(202)
    expect((await first.json()).run_id).toBe((await second.json()).run_id)
  })

  test('real SSE endpoint resumes persisted events after API restart', async ({ request }) => {
    const ids = process.env.BROWSER_EVENT_IDS!.split(',')
    const url = `/api/research-runs/${process.env.BROWSER_RUN_ID}/events`
    const full = await request.get(url)
    expect(full.status()).toBe(200)
    expect((await full.text()).split('\n').filter((line) => line.startsWith('id:'))).toEqual(ids.map((id) => `id: ${id}`))
    await stop()
    await start()
    const resumed = await request.get(url, { headers: { 'Last-Event-ID': ids[1] } })
    expect(resumed.status()).toBe(200)
    expect((await resumed.text()).split('\n').filter((line) => line.startsWith('id:'))).toEqual(ids.slice(2).map((id) => `id: ${id}`))
  })
})
