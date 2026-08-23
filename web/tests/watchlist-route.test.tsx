import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiRow = {
  alertThreshold: '0.025',
  createdAt: '2026-08-23T00:00:00+00:00',
  dailyResearch: true,
  enrichment: {
    kind: 'unavailable' as const,
    missing: ['market', 'research', 'earnings', 'data-quality'],
  },
  intradayMonitoring: false,
  symbol: 'NVDA',
  updatedAt: '2026-08-23T00:05:00+00:00',
}

async function mockWatchlistRead(implementation: () => unknown | Promise<unknown>) {
  vi.doMock('../lib/server/watchlist-api', async (importOriginal) => {
    const original = await importOriginal<typeof import('../lib/server/watchlist-api')>()
    return { ...original, listWatchlist: vi.fn(implementation) }
  })
}

afterEach(() => {
  vi.doUnmock('../lib/fixtures')
  vi.doUnmock('../lib/server/watchlist-api')
  vi.resetModules()
  delete process.env.WEB_DATA_MODE
  delete process.env.API_BASE_URL
})

describe('Watchlist route data boundaries', () => {
  it('loads the frozen snapshot only in explicit Fixture mode', async () => {
    process.env.WEB_DATA_MODE = 'fixture'
    await mockWatchlistRead(() => {
      throw new Error('FastAPI must not be called in Fixture mode')
    })
    const { default: WatchlistRoute } = await import('../app/watchlist/page')

    render(await WatchlistRoute())

    expect(screen.getByText('Fixture Mode')).toBeInTheDocument()
    expect(screen.getByRole('rowheader', { name: 'NVDA' })).toBeInTheDocument()
    expect(screen.queryByRole('alert', { name: 'Watchlist unavailable' })).not.toBeInTheDocument()
  })

  it('renders persisted configuration as Degraded without fixture enrichment', async () => {
    process.env.WEB_DATA_MODE = 'api'
    process.env.API_BASE_URL = 'http://127.0.0.1:8000'
    await mockWatchlistRead(() => [apiRow])
    const { default: WatchlistRoute } = await import('../app/watchlist/page')

    render(await WatchlistRoute())

    expect(screen.getByRole('status', { name: 'Market and research data unavailable' })).toHaveAttribute(
      'data-state',
      'degraded',
    )
    expect(screen.queryByText('Fixture Mode')).not.toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Persisted research watchlist' })
    expect(within(table).getByRole('rowheader', { name: 'NVDA' })).toBeInTheDocument()
    expect(within(table).getAllByText('Unavailable')).toHaveLength(7)
    expect(within(table).queryByText('$0.00')).not.toBeInTheDocument()
    expect(within(table).queryByText('ABSTAIN')).not.toBeInTheDocument()
    expect(within(table).queryByText('NO_ACTION')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'NVDA current market chart' })).not.toBeInTheDocument()
  })

  it('renders Failure and never loads Fixture data when the API read fails', async () => {
    process.env.WEB_DATA_MODE = 'api'
    process.env.API_BASE_URL = 'http://127.0.0.1:8000'
    await mockWatchlistRead(() => {
      throw new Error('API unavailable')
    })
    vi.doMock('../lib/fixtures', () => {
      throw new Error('Fixture fallback was loaded')
    })
    const { default: WatchlistRoute } = await import('../app/watchlist/page')

    render(await WatchlistRoute())

    expect(screen.getByRole('alert', { name: 'Watchlist unavailable' })).toHaveAttribute(
      'data-state',
      'failure',
    )
    expect(screen.queryByText('Fixture Mode')).not.toBeInTheDocument()
    expect(screen.queryByText('NVDA')).not.toBeInTheDocument()
    expect(screen.queryByText(/fixture-market/i)).not.toBeInTheDocument()
  })

  it('exposes persisted add, update, and delete controls with accessible names', async () => {
    process.env.WEB_DATA_MODE = 'api'
    process.env.API_BASE_URL = 'http://127.0.0.1:8000'
    await mockWatchlistRead(() => [apiRow])
    const { default: WatchlistRoute } = await import('../app/watchlist/page')

    render(await WatchlistRoute())

    expect(screen.getByRole('button', { name: 'Add to watchlist' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save NVDA settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete NVDA' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'NVDA daily research' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'NVDA intraday monitoring' })).not.toBeChecked()
    expect(screen.getByRole('textbox', { name: 'NVDA alert threshold' })).toHaveValue('0.025')
  })
})
