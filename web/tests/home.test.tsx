import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

describe('home page', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
    vi.doUnmock('../lib/server/live-data-api')
    vi.doUnmock('../lib/server/watchlist-api')
  })

  it('uses Today as the fixture-mode landing page without presenting fixtures as market data', async () => {
    vi.stubEnv('WEB_DATA_MODE', 'fixture')
    const { default: Home } = await import('../app/page')
    render(await Home())
    expect(screen.getByRole('heading', { name: 'Today' })).toBeInTheDocument()
    expect(screen.getByText('Fixture Mode')).toBeInTheDocument()
    expect(screen.getByText(/Frozen synthetic fixture · not current market data/i)).toBeInTheDocument()
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
  })

  it('keeps market facts visible when the portfolio API fails', async () => {
    vi.stubEnv('WEB_DATA_MODE', 'api')
    vi.stubEnv('API_BASE_URL', 'http://api.test')
    vi.doMock('../lib/server/watchlist-api', () => ({
      listWatchlist: vi.fn(async () => [{ symbol: 'NVDA' }]),
    }))
    vi.doMock('../lib/server/live-data-api', () => ({
      getMarketQuotes: vi.fn(async () => ({
        decisionTime: '2026-08-29T09:30:00Z',
        items: [{
          availableAt: '2026-08-29T09:20:00Z',
          close: '217.545',
          coverage: 'IEX',
          eventTime: '2026-08-28T04:00:00Z',
          provider: 'ALPACA',
          symbol: 'NVDA',
        }],
        missingSymbols: [],
        status: 'SUCCESS',
      })),
      getPortfolioSummary: vi.fn(async () => { throw new Error('portfolio unavailable') }),
      getProviderHealth: vi.fn(async () => ({
        mode: 'paper',
        providers: { alpaca: { configured: true, coverage: 'IEX', mode: 'read_only', status: 'SUCCESS' } },
      })),
    }))
    const { default: Home } = await import('../app/page')

    render(await Home())

    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    const degraded = screen.getByRole('status', { name: 'Some decision facts are unavailable' })
    expect(degraded).toHaveTextContent('5 unavailable facts')
    expect(screen.getByText('Decision Domain')).toBeInTheDocument()
    expect(degraded).toHaveTextContent('Portfolio API')
    expect(screen.queryByRole('list', { name: 'Degraded providers' })).not.toBeInTheDocument()
    expect(screen.queryByRole('alert', { name: 'Today unavailable' })).not.toBeInTheDocument()
  })

  it('surfaces degraded quote quality while keeping Today market facts visible', async () => {
    vi.stubEnv('WEB_DATA_MODE', 'api')
    vi.stubEnv('API_BASE_URL', 'http://api.test')
    vi.doMock('../lib/server/watchlist-api', () => ({
      listWatchlist: vi.fn(async () => [{ symbol: 'NVDA' }]),
    }))
    vi.doMock('../lib/server/live-data-api', () => ({
      getMarketQuotes: vi.fn(async () => ({
        decisionTime: '2026-08-29T09:30:00Z',
        items: [{
          availableAt: '2026-08-29T09:20:00Z', close: '217.545', coverage: 'IEX',
          eventTime: '2026-08-28T04:00:00Z', provider: 'ALPACA', symbol: 'NVDA',
        }],
        missingSymbols: [],
        status: 'DEGRADED',
      })),
      getPortfolioSummary: vi.fn(async () => ({
        cash: null, cashLedger: [], configuration: null, fills: [], initializedAt: null,
        latestNav: null, orders: [], performanceHistory: [], positions: [], riskDecisions: [],
        status: 'EMPTY', trading: 'paper_only',
      })),
      getProviderHealth: vi.fn(async () => ({
        mode: 'paper',
        providers: { alpaca: { configured: true, coverage: 'IEX', mode: 'read_only', status: 'SUCCESS' } },
      })),
    }))
    const { default: Home } = await import('../app/page')

    render(await Home())

    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Some decision facts are unavailable' })).toHaveTextContent(
      'Market quote quality',
    )
  })

  it('shows one canonical provider-health gap when the health API is unavailable', async () => {
    vi.stubEnv('WEB_DATA_MODE', 'api')
    vi.stubEnv('API_BASE_URL', 'http://api.test')
    vi.doMock('../lib/server/watchlist-api', () => ({
      listWatchlist: vi.fn(async () => [{ symbol: 'NVDA' }]),
    }))
    vi.doMock('../lib/server/live-data-api', () => ({
      getMarketQuotes: vi.fn(async () => ({
        decisionTime: '2026-08-29T09:30:00Z',
        items: [{
          availableAt: '2026-08-29T09:20:00Z', close: '217.545', coverage: 'IEX',
          eventTime: '2026-08-28T04:00:00Z', provider: 'ALPACA', symbol: 'NVDA',
        }],
        missingSymbols: [],
        status: 'SUCCESS',
      })),
      getPortfolioSummary: vi.fn(async () => ({
        cash: null, cashLedger: [], configuration: null, fills: [], initializedAt: null,
        latestNav: null, orders: [], performanceHistory: [], positions: [], riskDecisions: [],
        status: 'EMPTY', trading: 'paper_only',
      })),
      getProviderHealth: vi.fn(async () => { throw new Error('health unavailable') }),
    }))
    const { default: Home } = await import('../app/page')

    render(await Home())

    const degraded = screen.getByRole('status', { name: 'Some decision facts are unavailable' })
    expect(degraded).toHaveTextContent('Provider health')
    expect(degraded).not.toHaveTextContent('Provider health API')
    expect(degraded.querySelectorAll('li')).toHaveLength(5)
  })
})
