import { describe, expect, it, vi } from 'vitest'

import {
  getMarketQuotes,
  getPortfolioSummary,
  getProviderHealth,
  getStockResearch,
  LiveDataApiError,
} from '../lib/server/live-data-api'

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

const options = { baseUrl: 'http://api.test', decisionTime: '2026-08-29T09:30:00Z' }

describe('live data API client', () => {
  it('validates point-in-time quote Decimal strings and provenance', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      status: 'SUCCESS',
      decision_time: options.decisionTime,
      missing_symbols: [],
      items: [{
        symbol: 'NVDA', provider: 'ALPACA', coverage: 'IEX', feed_type: 'price_bars',
        event_time: '2026-08-28T04:00:00Z', available_at: '2026-08-29T09:20:00Z',
        ingested_at: '2026-08-29T09:20:01Z', content_hash: 'a'.repeat(64),
        raw_object_key: `live/ALPACA/price_bars/${'a'.repeat(64)}.json`, close: '217.545',
        open: '220', high: '221', low: '216', volume: '5357434', session: 'REGULAR',
      }],
    }))

    const result = await getMarketQuotes({ ...options, fetchImpl }, ['NVDA'])

    expect(result.items[0]).toMatchObject({ symbol: 'NVDA', close: '217.545', provider: 'ALPACA' })
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/market-data/quotes?'),
      expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }),
    )
  })

  it('rejects malformed provider responses instead of substituting fixtures', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ status: 'SUCCESS', items: [{ close: 217.5 }] }))

    await expect(getMarketQuotes({ ...options, fetchImpl }, ['NVDA'])).rejects.toMatchObject({
      kind: 'contract',
    })
  })

  it('loads runtime provider health, portfolio facts, and persisted research independently', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/providers/health')) return jsonResponse({
        mode: 'paper', providers: { alpaca: { configured: true, mode: 'read_only', status: 'SUCCESS', coverage: 'IEX' } },
      })
      if (url.includes('/portfolio?')) return jsonResponse({ latest_nav: null, trading: 'paper_only' })
      return jsonResponse([])
    })

    await expect(getProviderHealth({ ...options, fetchImpl })).resolves.toMatchObject({ mode: 'paper' })
    await expect(getPortfolioSummary({ ...options, fetchImpl })).resolves.toEqual({ latestNav: null, trading: 'paper_only' })
    await expect(getStockResearch({ ...options, fetchImpl }, 'NVDA')).resolves.toEqual([])
  })

  it('classifies network and HTTP failures without exposing upstream bodies', async () => {
    const network = vi.fn(async () => { throw new TypeError('private network detail') })
    await expect(getProviderHealth({ ...options, fetchImpl: network })).rejects.toMatchObject({ kind: 'unavailable' })

    const response = vi.fn(async () => new Response('private upstream body', { status: 503 }))
    const error = await getProviderHealth({ ...options, fetchImpl: response }).catch((caught) => caught)
    expect(error).toBeInstanceOf(LiveDataApiError)
    expect(error).toMatchObject({ kind: 'response', status: 503 })
    expect((error as Error).message).not.toContain('private upstream body')
  })
})
