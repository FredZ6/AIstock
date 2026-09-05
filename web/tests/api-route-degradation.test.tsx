import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
  vi.doUnmock('../lib/server/live-data-api')
})

describe('API route partial degradation', () => {
  it('keeps persisted research visible when the current quote fails', async () => {
    vi.stubEnv('WEB_DATA_MODE', 'api')
    vi.stubEnv('API_BASE_URL', 'http://api.test')
    vi.doMock('../lib/server/live-data-api', () => ({
      getDataQuality: vi.fn(async () => []),
      getMarketQuotes: vi.fn(async () => { throw new Error('quote unavailable') }),
      getStockResearch: vi.fn(async () => ({ financialFacts: [], secFilings: [], records: [{
        asOf: '2026-08-20T20:00:00Z',
        confidence: '0.7',
        direction: 'BULLISH',
        horizon: 'MEDIUM',
        id: 'thesis-1',
        opinion: 'BULLISH',
        summary: 'Persisted thesis remains visible.',
        symbol: 'NVDA',
      }]})),
    }))
    const { default: ResearchRoute } = await import('../app/research/[symbol]/page')

    render(await ResearchRoute({ params: Promise.resolve({ symbol: 'NVDA' }) }))

    expect(screen.getByText('Persisted thesis remains visible.')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Current market reference unavailable' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('SEC filing quality')
    expect(screen.getByRole('status')).toHaveTextContent('SEC facts quality')
    expect(screen.queryByRole('alert', { name: 'NVDA research unavailable' })).not.toBeInTheDocument()
  })

  it('surfaces degraded quote quality while keeping research and the quote visible', async () => {
    vi.stubEnv('WEB_DATA_MODE', 'api')
    vi.stubEnv('API_BASE_URL', 'http://api.test')
    vi.doMock('../lib/server/live-data-api', () => ({
      getDataQuality: vi.fn(async () => []),
      getMarketQuotes: vi.fn(async () => ({
        decisionTime: '2026-08-29T09:30:00Z',
        items: [{
          availableAt: '2026-08-29T09:20:00Z', close: '217.545', coverage: 'IEX',
          eventTime: '2026-08-28T04:00:00Z', provider: 'ALPACA', symbol: 'NVDA',
        }],
        missingSymbols: [],
        status: 'DEGRADED',
      })),
      getStockResearch: vi.fn(async () => ({ financialFacts: [], secFilings: [], records: [{
        asOf: '2026-08-20T20:00:00Z', confidence: '0.7', direction: 'BULLISH',
        horizon: 'MEDIUM', id: 'thesis-1', opinion: 'BULLISH',
        summary: 'Persisted thesis remains visible.', symbol: 'NVDA',
      }]})),
    }))
    const { default: ResearchRoute } = await import('../app/research/[symbol]/page')

    render(await ResearchRoute({ params: Promise.resolve({ symbol: 'NVDA' }) }))

    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Market quote quality')
  })
})
