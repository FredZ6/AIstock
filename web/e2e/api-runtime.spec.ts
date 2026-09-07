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
    await page.getByRole('link', { name: 'Try again' }).click()
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
    await expect(page.getByRole('list', { name: 'Durable run events' }).getByRole('listitem')).toHaveCount(ids.length)
    const accessibility = await new AxeBuilder({ page }).analyze()
    expect(accessibility.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')).toEqual([])
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
