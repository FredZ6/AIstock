import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

import { ApiWatchlistPage } from '../components/watchlist/watchlist-page'

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

function marketBar(close: string, eventTime: string, contentHash = 'a'.repeat(64)) {
  return {
    availableAt: eventTime,
    close,
    conflict: false,
    contentHash,
    coverage: 'IEX' as const,
    eventTime,
    feedType: 'price_bars',
    high: close,
    ingestedAt: eventTime,
    low: close,
    open: close,
    provider: 'ALPACA',
    rawObjectKey: `live/ALPACA/price_bars/${contentHash}.json`,
    session: 'REGULAR' as const,
    symbol: 'NVDA',
    timeframe: '1Day' as const,
    volume: '1000',
  }
}

async function mockWatchlistRead(implementation: () => unknown | Promise<unknown>) {
  vi.doMock('../lib/server/watchlist-api', async (importOriginal) => {
    const original = await importOriginal<typeof import('../lib/server/watchlist-api')>()
    return { ...original, listWatchlist: vi.fn(implementation) }
  })
}

async function mockMarketQuotes(implementation: (...args: unknown[]) => unknown | Promise<unknown>) {
  vi.doMock('../lib/server/live-data-api', async (importOriginal) => {
    const original = await importOriginal<typeof import('../lib/server/live-data-api')>()
    return {
      ...original,
      getHistoricalBars: vi.fn(async () => ({ decisionTime: '2026-08-29T09:30:00Z', items: [], status: 'FAILURE' })),
      getMarketQuotes: vi.fn(async (...args: unknown[]) => implementation(...args)),
      getStockResearch: vi.fn(async () => ({
        earningsEvents: [], financialFacts: [], newsArticles: [], optionSnapshots: [], records: [],
        secFilings: [], unavailableDomains: ['EARNINGS'],
      })),
    }
  })
}

afterEach(() => {
  vi.doUnmock('../lib/fixtures')
  vi.doUnmock('../lib/server/watchlist-api')
  vi.doUnmock('../lib/server/live-data-api')
  vi.doUnmock('../lib/server/live-data-diagnostics')
  vi.resetModules()
  vi.useRealTimers()
  delete process.env.WEB_DATA_MODE
  delete process.env.API_BASE_URL
})

describe('Watchlist route data boundaries', () => {
  it('uses the request decision time as the page point-in-time context', async () => {
    let queriedDecisionTime: string | undefined
    let reportedError: unknown
    process.env.WEB_DATA_MODE = 'api'
    process.env.API_BASE_URL = 'http://127.0.0.1:8000'
    await mockWatchlistRead(() => [apiRow])
    await mockMarketQuotes((query) => {
      queriedDecisionTime = (query as { decisionTime: string }).decisionTime
      return { items: [], missingSymbols: ['NVDA'], status: 'FAILURE' }
    })
    vi.doMock('../lib/server/live-data-diagnostics', async (importOriginal) => {
      const original = await importOriginal<typeof import('../lib/server/live-data-diagnostics')>()
      return {
        ...original,
        reportLiveDataFailure: vi.fn((_route, _domain, error) => {
          reportedError = error
        }),
      }
    })
    const { default: WatchlistRoute } = await import('../app/watchlist/page')

    const { container } = render(await WatchlistRoute())

    expect(reportedError).toBeUndefined()
    expect(queriedDecisionTime).toBeDefined()
    expect(Array.from(container.querySelectorAll('[aria-label="Snapshot time"] time'))).not.toHaveLength(0)
    expect(Array.from(container.querySelectorAll('[aria-label="Snapshot time"] time')).every(
      (element) => element.getAttribute('datetime') === queriedDecisionTime,
    )).toBe(true)
  })

  it('does not label persisted market quotes unavailable when they are present', () => {
    render(<ApiWatchlistPage
      asOf="2026-08-29T09:30:00Z"
      items={[apiRow]}
      quotes={[{
        availableAt: '2026-08-29T09:20:00Z',
        close: '217.545',
        coverage: 'IEX',
        eventTime: '2026-08-28T04:00:00Z',
        provider: 'ALPACA',
        symbol: 'NVDA',
      }]}
    />)

    expect(screen.getByRole('status', { name: 'Research enrichment unavailable' })).toHaveTextContent(
      'ALPACA market quotes remain visible',
    )
    expect(screen.queryByRole('status', { name: 'Market and research data unavailable' })).not.toBeInTheDocument()
    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    expect(screen.queryByText('STALE')).not.toBeInTheDocument()
  })

  it('labels a persisted quote stale relative to the visible point-in-time cutoff', () => {
    render(<ApiWatchlistPage
      asOf="2026-09-08T09:30:00Z"
      items={[apiRow]}
      quotes={[{
        availableAt: '2026-09-03T09:20:00Z',
        close: '217.545',
        coverage: 'IEX',
        eventTime: '2026-09-03T09:19:00Z',
        provider: 'ALPACA',
        symbol: 'NVDA',
      }]}
    />)

    const row = within(screen.getByRole('list', { name: 'Ranked research watchlist' })).getByRole('listitem')
    expect(within(row).getByText('STALE')).toBeInTheDocument()
    expect(row).toHaveTextContent('Quote older than 24 hours at snapshot')
    expect(row).toHaveTextContent('Persisted Sep 3, 2026')
  })

  it('does not discard a degraded quote-quality status when every symbol has a price', () => {
    render(<ApiWatchlistPage
      asOf="2026-08-29T09:30:00Z"
      items={[apiRow]}
      quoteStatus="DEGRADED"
      quotes={[{
        availableAt: '2026-08-29T09:20:00Z',
        close: '217.545',
        coverage: 'IEX',
        eventTime: '2026-08-28T04:00:00Z',
        provider: 'ALPACA',
        symbol: 'NVDA',
      }]}
    />)

    expect(screen.getByRole('status', { name: 'Market and research data unavailable' })).toHaveTextContent(
      'Market quote quality',
    )
  })

  it('uses the server-provided request time for an empty API watchlist', () => {
    const asOf = '2026-08-23T08:30:00.000Z'

    const { container } = render(<ApiWatchlistPage asOf={asOf} items={[]} quotes={[]} />)

    expect(Array.from(container.querySelectorAll('time'))).not.toHaveLength(0)
    expect(Array.from(container.querySelectorAll('time')).every(
      (element) => element.getAttribute('datetime') === asOf,
    )).toBe(true)
  })

  it('loads the frozen snapshot only in explicit Fixture mode', async () => {
    process.env.WEB_DATA_MODE = 'fixture'
    await mockWatchlistRead(() => {
      throw new Error('FastAPI must not be called in Fixture mode')
    })
    const { default: WatchlistRoute } = await import('../app/watchlist/page')

    render(await WatchlistRoute())

    expect(screen.getByText('Fixture Mode')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Ranked research watchlist' }))
      .getByRole('link', { name: 'NVDA' })).toBeInTheDocument()
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
    const list = screen.getByRole('list', { name: 'Ranked research watchlist' })
    expect(within(list).getByRole('link', { name: 'NVDA' })).toBeInTheDocument()
    expect(within(list).getByText('Price unavailable')).toBeInTheDocument()
    expect(within(list).getByText('Trend unavailable')).toBeInTheDocument()
    expect(within(list).getByText('Change unavailable')).toBeInTheDocument()
    expect(within(list).queryByText('$0.00')).not.toBeInTheDocument()
    expect(within(list).queryByText('ABSTAIN')).not.toBeInTheDocument()
    expect(within(list).queryByText('NO_ACTION')).not.toBeInTheDocument()
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

  it('presents persisted symbols as one ranked quote list with honest missing trend facts', () => {
    render(<ApiWatchlistPage
      asOf="2026-08-29T09:30:00Z"
      items={[apiRow]}
      quotes={[{
        availableAt: '2026-08-29T09:20:00Z',
        close: '217.545',
        coverage: 'IEX',
        eventTime: '2026-08-28T04:00:00Z',
        provider: 'ALPACA',
        symbol: 'NVDA',
      }]}
    />)

    const list = screen.getByRole('list', { name: 'Ranked research watchlist' })
    const row = within(list).getByRole('listitem')
    expect(row).toHaveTextContent('NVDA')
    expect(row).toHaveTextContent('NVIDIA Corporation')
    expect(row).toHaveTextContent('USD 217.55')
    expect(row).toHaveTextContent('Trend unavailable')
    expect(row).toHaveTextContent('Change unavailable')
    expect(row).toHaveTextContent('ALPACA · IEX')
    expect(row).toHaveTextContent('Persisted Aug 29, 2026')
  })

  it('renders persisted bar change, compact trend, provenance, and earnings schedule', () => {
    const contentHash = 'a'.repeat(64)

    render(<ApiWatchlistPage
      asOf="2026-08-29T09:30:00Z"
      earningsBySymbol={{
        NVDA: [{
          availableAt: '2026-08-29T09:20:00Z', contentHash: 'b'.repeat(64), currency: 'USD',
          estimate: '0.95', eventDate: '2026-09-20', eventTime: '2026-08-29T09:00:00Z',
          fiscalDateEnd: '2026-06-30', id: 'earnings-1', provider: 'ALPHA_VANTAGE',
          rawObjectKey: 'live/earnings/NVDA.csv',
        }],
      }}
      historiesBySymbol={{ NVDA: [
        marketBar('100', '2026-08-27T20:00:00Z'),
        marketBar('105', '2026-08-28T20:00:00Z'),
        marketBar('110', '2026-08-29T09:20:00Z'),
      ] }}
      items={[apiRow]}
      quotes={[{
        availableAt: '2026-08-29T09:20:00Z', close: '110', coverage: 'IEX',
        eventTime: '2026-08-29T09:20:00Z', provider: 'ALPACA', symbol: 'NVDA',
      }]}
    />)

    const row = within(screen.getByRole('list', { name: 'Ranked research watchlist' })).getByRole('listitem')
    expect(within(row).getByText('+4.76%')).toBeInTheDocument()
    expect(within(row).getByRole('img', { name: 'NVDA persisted 3-session trend' })).toBeInTheDocument()
    expect(row).toHaveTextContent('PIT cutoff Aug 29, 2026')
    expect(row).toHaveTextContent(`live/ALPACA/price_bars/${contentHash}.json`)
    const configuration = screen.getByRole('region', { name: 'Watchlist configuration' })
    fireEvent.click(within(configuration).getByText('NVDA settings'))
    fireEvent.click(within(configuration).getByText('Next earnings Sep 20, 2026'))
    expect(within(configuration).getByText(/ALPHA_VANTAGE/)).toBeInTheDocument()
    expect(within(configuration).getByText('live/earnings/NVDA.csv')).toBeInTheDocument()
  })

  it('keeps stale trend history explicit even when the current quote is fresh', () => {
    render(<ApiWatchlistPage
      asOf="2026-09-08T09:30:00Z"
      earningsBySymbol={{ NVDA: [] }}
      historiesBySymbol={{ NVDA: [
        marketBar('100', '2026-09-01T20:00:00Z'),
        marketBar('101', '2026-09-02T20:00:00Z'),
      ] }}
      items={[apiRow]}
      quotes={[{
        availableAt: '2026-09-08T09:20:00Z', close: '102', coverage: 'IEX',
        eventTime: '2026-09-08T09:19:00Z', provider: 'ALPACA', symbol: 'NVDA',
      }]}
    />)

    expect(screen.getByRole('status')).toHaveTextContent('NVDA trend stale')
    const row = within(screen.getByRole('list', { name: 'Ranked research watchlist' })).getByRole('listitem')
    expect(row).toHaveTextContent('Historical trend older than 24 hours at snapshot')
  })

  it('loads bar and earnings enrichment with the same aware decision cutoff', async () => {
    let historyCutoff: string | undefined
    let researchCutoff: string | undefined
    process.env.WEB_DATA_MODE = 'api'
    process.env.API_BASE_URL = 'http://127.0.0.1:8000'
    await mockWatchlistRead(() => [apiRow])
    vi.doMock('../lib/server/live-data-api', async (importOriginal) => {
      const original = await importOriginal<typeof import('../lib/server/live-data-api')>()
      return {
        ...original,
        getHistoricalBars: vi.fn(async (options: { decisionTime: string }) => {
          historyCutoff = options.decisionTime
          return { decisionTime: options.decisionTime, items: [], status: 'FAILURE' }
        }),
        getMarketQuotes: vi.fn(async () => ({ items: [], missingSymbols: ['NVDA'], status: 'FAILURE' })),
        getStockResearch: vi.fn(async (options: { decisionTime: string }) => {
          researchCutoff = options.decisionTime
          return {
            earningsEvents: [], financialFacts: [], newsArticles: [], optionSnapshots: [],
            records: [], secFilings: [], unavailableDomains: ['EARNINGS'],
          }
        }),
      }
    })
    const { default: WatchlistRoute } = await import('../app/watchlist/page')

    render(await WatchlistRoute())

    expect(historyCutoff).toBeDefined()
    expect(researchCutoff).toBe(historyCutoff)
  })

  it('keeps all persisted watchlist mutations in one labelled configuration region', () => {
    render(<ApiWatchlistPage asOf="2026-08-29T09:30:00Z" items={[apiRow]} quotes={[]} />)

    const configuration = screen.getByRole('region', { name: 'Watchlist configuration' })
    expect(within(configuration).getByRole('button', { name: 'Add to watchlist' })).toBeInTheDocument()
    expect(within(configuration).getByRole('button', { name: 'Delete NVDA' })).toBeInTheDocument()
    expect(within(configuration).getByRole('checkbox', { name: 'NVDA daily research' })).toBeInTheDocument()
    expect(within(configuration).getByRole('checkbox', { name: 'NVDA intraday monitoring' })).toBeInTheDocument()
    expect(within(configuration).getByRole('textbox', { name: 'NVDA alert threshold' })).toBeInTheDocument()
    expect(within(configuration).getByText('Earnings schedule unavailable')).toBeInTheDocument()
    const disclosures = configuration.querySelectorAll('.watchlist-config-list details')
    expect(disclosures).toHaveLength(1)
    expect(disclosures[0]).not.toHaveAttribute('open')
    expect(within(configuration).getByText('NVDA settings')).toBeInTheDocument()
  })
})
