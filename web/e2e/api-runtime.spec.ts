import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { expect, test } from '@playwright/test'

test.describe('isolated real API runtime', () => {
  test.skip(process.env.RUN_API_BROWSER !== '1', 'Requires isolated database harness')
  test.describe.configure({ mode: 'serial' })
  let api: ChildProcess | undefined
  const base = 'http://127.0.0.1:8107'

  async function start() {
    api = spawn('../.venv/bin/python', ['-m', 'uvicorn', 'browser_api:app', '--host', '127.0.0.1', '--port', '8107'], {
      env: { ...process.env, PYTHONPATH: '../backend/src:../backend/tests' }, stdio: 'ignore',
    })
    await expect.poll(async () => {
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
    await expect(page.getByRole('table', { name: 'Research watchlist' })).toBeVisible()
    await expect(page.getByRole('rowheader', { name: 'NVDA', exact: true })).toBeVisible()
    await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
    await stop()
    await page.reload()
    await expect(page.getByRole('alert', { name: 'Watchlist unavailable' })).toBeVisible()
    await expect(page.getByRole('table', { name: 'Research watchlist' })).toHaveCount(0)
    await start()
    await page.getByRole('link', { name: 'Try again' }).click()
    await expect(page.getByRole('table', { name: 'Research watchlist' })).toBeVisible()
    await expect(page.getByText('Fixture Mode', { exact: true })).toHaveCount(0)
  })

  test('all eight routes render API states without fixture content or horizontal overflow', async ({ page }) => {
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
    await expect(page.getByRole('region', { name: 'Persisted run metadata' })).toBeVisible()
  })

  test('real SSE endpoint resumes persisted events after API restart', async ({ request }) => {
    const ids = process.env.BROWSER_EVENT_IDS!.split(',')
    const url = `${base}/api/v1/events?run_id=${process.env.BROWSER_RUN_ID}`
    const full = await request.get(url)
    expect(full.status()).toBe(200)
    expect((await full.text()).split('\n').filter((line) => line.startsWith('id:'))).toEqual(ids.map((id) => `id: ${id}`))
    await stop()
    await start()
    const resumed = await request.get(url, { headers: { 'Last-Event-ID': ids[1] } })
    expect(resumed.status()).toBe(200)
    expect((await resumed.text()).split('\n').filter((line) => line.startsWith('id:'))).toEqual([`id: ${ids[2]}`])
  })
})
