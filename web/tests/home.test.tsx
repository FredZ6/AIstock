import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

describe('home page', () => {
  afterEach(() => {
    vi.useRealTimers()
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
      getAlerts: vi.fn(async () => ({ items: [], nextCursor: null })),
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
      getStockResearch: vi.fn(async () => ({ financialFacts: [], records: [], secFilings: [] })),
    }))
    const { default: Home } = await import('../app/page')

    render(await Home())

    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    const degraded = screen.getByRole('status', { name: 'Some decision facts are unavailable' })
    expect(degraded).toHaveTextContent('1 unavailable fact')
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
      getAlerts: vi.fn(async () => ({ items: [], nextCursor: null })),
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
      getStockResearch: vi.fn(async () => ({ financialFacts: [], records: [], secFilings: [] })),
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
      getAlerts: vi.fn(async () => ({ items: [], nextCursor: null })),
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
      getStockResearch: vi.fn(async () => ({ financialFacts: [], records: [], secFilings: [] })),
    }))
    const { default: Home } = await import('../app/page')

    render(await Home())

    const degraded = screen.getByRole('status', { name: 'Some decision facts are unavailable' })
    expect(degraded).toHaveTextContent('Provider health')
    expect(degraded).not.toHaveTextContent('Provider health API')
    expect(degraded.querySelectorAll('li')).toHaveLength(2)
  })

  it('reaches a truthful Success state and renders all available authoritative facts', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-09T14:30:00Z'))
    vi.stubEnv('WEB_DATA_MODE', 'api')
    vi.stubEnv('API_BASE_URL', 'http://api.test')
    vi.doMock('../lib/server/watchlist-api', () => ({
      listWatchlist: vi.fn(async () => [{ symbol: 'NVDA' }]),
    }))
    vi.doMock('../lib/server/live-data-api', () => ({
      getAlerts: vi.fn(async () => ({ items: [{
        acknowledgedAt: null, acknowledgedBy: null, alertKey: 'NVDA:gap', conditions: [],
        correlationId: 'correlation-1', createdAt: '2026-09-09T14:20:00Z', dataQuality: {},
        eventTime: '2026-09-09T14:15:00Z', id: 'alert-1', materiality: '0.8', metrics: {},
        ruleId: 'gap', ruleVersion: 'v1', severity: 'HIGH', symbol: 'NVDA',
      }], nextCursor: null })),
      getMarketQuotes: vi.fn(async () => ({
        decisionTime: '2026-09-09T14:30:00Z', items: [{ availableAt: '2026-09-09T14:29:00Z',
          close: '217.55', coverage: 'IEX', eventTime: '2026-09-09T14:28:00Z', provider: 'ALPACA', symbol: 'NVDA' }],
        missingSymbols: [], status: 'SUCCESS',
      })),
      getPortfolioSummary: vi.fn(async () => ({
        cash: { balance: '100000', currency: 'USD' }, cashLedger: [], configuration: { currency: 'USD', id: 'p1', initialCash: '100000', name: 'AI Portfolio' }, fills: [], initializedAt: '2026-09-01T00:00:00Z',
        latestNav: { eventTime: '2026-09-09T14:25:00Z', nav: '100425.18', portfolioId: 'p1' },
        orders: [], performanceHistory: [], positions: [], riskDecisions: [], status: 'SUCCESS', trading: 'paper_only',
      })),
      getProviderHealth: vi.fn(async () => ({
        mode: 'paper', providers: { alpaca: { configured: true, coverage: 'IEX', mode: 'read_only', status: 'SUCCESS' } },
      })),
      getStockResearch: vi.fn(async () => ({ financialFacts: [], secFilings: [], records: [{
        asOf: '2026-09-09T14:00:00Z', confidence: '0.82', direction: 'UP', horizon: '12M', id: 'r1',
        opinion: 'BULLISH', summary: 'Demand remains durable.', symbol: 'NVDA',
      }] })),
    }))
    const { default: Home } = await import('../app/page')

    render(await Home())

    expect(screen.queryByRole('status', { name: 'Some decision facts are unavailable' })).not.toBeInTheDocument()
    expect(screen.getByText('Demand remains durable.')).toBeInTheDocument()
    expect(screen.getByText('gap · v1')).toBeInTheDocument()
    expect(screen.getByText('ALPACA · IEX · SUCCESS')).toBeInTheDocument()
    expect(screen.getByText(/100,425\.18/)).toBeInTheDocument()
    expect(screen.getByText('Sep 9, 2026, 10:30 AM')).toBeInTheDocument()
  })
})
