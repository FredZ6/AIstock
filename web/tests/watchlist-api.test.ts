import { afterEach, describe, expect, it, vi } from 'vitest'

import { readApiBaseUrl, readWebDataConfig, readWebDataMode } from '../lib/server/data-mode'
import {
  addWatchlistItem,
  deleteWatchlistItem,
  listWatchlist,
  patchWatchlistItem,
  refreshWatchlistMarketData,
  WatchlistApiError,
} from '../lib/server/watchlist-api'

const validRow = {
  symbol: 'NVDA',
  display_order: 1,
  daily_research: true,
  intraday_monitoring: false,
  thresholds: { return_5m: '0.025' },
  created_at: '2026-08-23T00:00:00+00:00',
  updated_at: '2026-08-23T00:05:00+00:00',
}

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

afterEach(() => {
  vi.useRealTimers()
})

describe('web data mode', () => {
  it.each(['api', 'fixture'] as const)('accepts explicit %s mode', (mode) => {
    expect(readWebDataMode({ WEB_DATA_MODE: mode })).toBe(mode)
  })

  it.each([undefined, '', 'production', 'API'])('rejects missing or unknown mode %s', (mode) => {
    expect(() => readWebDataMode({ WEB_DATA_MODE: mode })).toThrow(
      'WEB_DATA_MODE must be explicitly set to api or fixture',
    )
  })

  it('accepts a server-only HTTP API base URL', () => {
    expect(readApiBaseUrl({ API_BASE_URL: 'http://127.0.0.1:8000/' })).toBe(
      'http://127.0.0.1:8000/',
    )
  })

  it.each([undefined, '', 'localhost:8000', 'file:///tmp/api'])('rejects invalid API URL %s', (url) => {
    expect(() => readApiBaseUrl({ API_BASE_URL: url })).toThrow(
      'API_BASE_URL must be an absolute HTTP(S) URL in API mode',
    )
  })

  it('builds Fixture configuration without accepting a public API URL', () => {
    expect(readWebDataConfig({
      API_BASE_URL: undefined,
      NEXT_PUBLIC_API_BASE_URL: 'https://browser-visible.example',
      WEB_DATA_MODE: 'fixture',
    })).toEqual({ mode: 'fixture' })
  })

  it('requires the server-only API URL when building API configuration', () => {
    expect(() => readWebDataConfig({
      NEXT_PUBLIC_API_BASE_URL: 'https://browser-visible.example',
      WEB_DATA_MODE: 'api',
    })).toThrow('API_BASE_URL must be an absolute HTTP(S) URL in API mode')

    expect(readWebDataConfig({
      API_BASE_URL: 'http://127.0.0.1:8000',
      WEB_DATA_MODE: 'api',
    })).toEqual({ baseUrl: 'http://127.0.0.1:8000/', mode: 'api' })
  })
})

describe('watchlist API read client', () => {
  it('loads and validates the persisted watchlist without caching', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse([validRow]))

    const result = await listWatchlist({ baseUrl: 'http://api.test', fetchImpl })

    expect(result[0]).toMatchObject({ symbol: 'NVDA', displayOrder: 1, alertThreshold: '0.025' })
    expect(fetchImpl).toHaveBeenCalledOnce()
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api.test/api/v1/watchlist',
      expect.objectContaining({
        cache: 'no-store',
        headers: { Accept: 'application/json' },
        method: 'GET',
        signal: expect.any(AbortSignal),
      }),
    )
  })

  it('classifies network failures as unavailable', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('private network detail')
    })

    await expect(listWatchlist({ baseUrl: 'http://api.test', fetchImpl })).rejects.toMatchObject({
      kind: 'unavailable',
      message: 'Watchlist API is unavailable',
    })
  })

  it('aborts a read that exceeds its timeout', async () => {
    vi.useFakeTimers()
    const fetchImpl = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }))

    const request = listWatchlist({ baseUrl: 'http://api.test', fetchImpl, timeoutMs: 10 })
    const assertion = expect(request).rejects.toMatchObject({ kind: 'unavailable' })
    await vi.advanceTimersByTimeAsync(10)

    await assertion
  })

  it('classifies non-success responses without leaking their body', async () => {
    const fetchImpl = vi.fn(async () => new Response('secret upstream diagnostic', { status: 503 }))

    const error = await listWatchlist({ baseUrl: 'http://api.test', fetchImpl }).catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(WatchlistApiError)
    expect(error).toMatchObject({ kind: 'response', status: 503 })
    expect((error as Error).message).not.toContain('secret upstream diagnostic')
  })

  it.each([
    ['invalid JSON', new Response('{', { status: 200 })],
    ['an invalid contract', jsonResponse([{ ...validRow, symbol: 'nvda' }])],
  ])('classifies %s as a contract failure', async (_label, response) => {
    const fetchImpl = vi.fn(async () => response)

    await expect(listWatchlist({ baseUrl: 'http://api.test', fetchImpl })).rejects.toMatchObject({
      kind: 'contract',
      message: 'Watchlist API returned an invalid response',
    })
  })
})

describe('watchlist API mutations', () => {
  const invalidSymbolFetch = vi.fn(async () => jsonResponse(validRow))

  it('creates a watchlist item through the locked POST contract', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(validRow, 201))

    const result = await addWatchlistItem(
      { baseUrl: 'http://api.test', fetchImpl },
      {
        symbol: 'NVDA',
        dailyResearch: true,
        intradayMonitoring: true,
        thresholds: {},
      },
    )

    expect(result).toMatchObject({ displayOrder: 1, symbol: 'NVDA' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api.test/api/v1/watchlist',
      expect.objectContaining({
        body: JSON.stringify({
          symbol: 'NVDA',
          daily_research: true,
          intraday_monitoring: true,
          thresholds: {},
        }),
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        method: 'POST',
      }),
    )
  })

  it('updates a watchlist item through the locked PATCH contract', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      ...validRow,
      daily_research: false,
      thresholds: { return_5m: '0.03' },
    }))

    const result = await patchWatchlistItem(
      { baseUrl: 'http://api.test', fetchImpl },
      'NVDA',
      { dailyResearch: false, thresholds: { return_5m: '0.03' } },
    )

    expect(result).toMatchObject({ dailyResearch: false, displayOrder: 1, alertThreshold: '0.03' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api.test/api/v1/watchlist/NVDA',
      expect.objectContaining({
        body: JSON.stringify({
          daily_research: false,
          thresholds: { return_5m: '0.03' },
        }),
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        method: 'PATCH',
      }),
    )
  })

  it('deletes a watchlist item only when the API confirms 204', async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }))

    await expect(
      deleteWatchlistItem({ baseUrl: 'http://api.test', fetchImpl }, 'AAPL.B'),
    ).resolves.toBeUndefined()
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api.test/api/v1/watchlist/AAPL.B',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('rejects a non-204 delete response', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(validRow))

    await expect(
      deleteWatchlistItem({ baseUrl: 'http://api.test', fetchImpl }, 'NVDA'),
    ).rejects.toMatchObject({ kind: 'contract', status: 200 })
  })

  it.each([
    ['add', () => addWatchlistItem(
      { baseUrl: 'http://api.test', fetchImpl: invalidSymbolFetch },
      { symbol: 'nvda!', dailyResearch: true, intradayMonitoring: true, thresholds: {} },
    )],
    ['patch', () => patchWatchlistItem(
      { baseUrl: 'http://api.test', fetchImpl: invalidSymbolFetch },
      'nvda!',
      { dailyResearch: false },
    )],
    ['delete', () => deleteWatchlistItem(
      { baseUrl: 'http://api.test', fetchImpl: invalidSymbolFetch },
      'nvda!',
    )],
  ])('rejects an invalid symbol before %s reaches fetch', async (_operation, invoke) => {
    await expect(invoke()).rejects.toMatchObject({ kind: 'contract' })
    expect(invalidSymbolFetch).not.toHaveBeenCalled()
  })

  it('validates mutation response rows with the same strict contract', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ...validRow, updated_at: 'naive' }, 201))

    await expect(addWatchlistItem(
      { baseUrl: 'http://api.test', fetchImpl },
      { symbol: 'NVDA', dailyResearch: true, intradayMonitoring: true, thresholds: {} },
    )).rejects.toMatchObject({ kind: 'contract' })
  })
})

describe('Watchlist market-data refresh client', () => {
  const validRefresh = {
    status: 'queued',
    job_ids: ['72e81d35-9400-4d2b-91d4-3f2aa4d12d15'],
    symbol_count: 1,
    requested_at: '2026-10-05T12:30:00+00:00',
    data_cutoff: '2026-10-02T16:00:00Z',
    timeframe: '1Day',
    feed: 'IEX',
    message: 'Latest Watchlist market-data jobs were queued.',
  }

  it('posts the exact refresh route with a server-only bearer token and parses the 202 contract', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(validRefresh, 202))
    const result = await refreshWatchlistMarketData({
      adminToken: 'server-secret',
      baseUrl: 'http://api.test',
      fetchImpl,
    })

    expect(result).toEqual({
      dataCutoff: validRefresh.data_cutoff,
      feed: 'IEX',
      jobIds: validRefresh.job_ids,
      message: validRefresh.message,
      requestedAt: validRefresh.requested_at,
      status: 'queued',
      symbolCount: 1,
      timeframe: '1Day',
    })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api.test/api/v1/watchlist/refresh-market-data',
      expect.objectContaining({
        cache: 'no-store',
        headers: { Accept: 'application/json', Authorization: 'Bearer server-secret' },
        method: 'POST',
        signal: expect.any(AbortSignal),
      }),
    )
  })

  it('accepts an explicit unavailable 202 result without turning it into a transport error', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      ...validRefresh,
      status: 'unavailable',
      job_ids: [],
      data_cutoff: null,
      timeframe: null,
      feed: null,
      message: 'Alpaca IEX entitlement is unavailable.',
    }, 202))

    await expect(refreshWatchlistMarketData({
      adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl,
    })).resolves.toMatchObject({ status: 'unavailable', jobIds: [], dataCutoff: null })
  })

  it('accepts the backend no-symbols and session-unavailable results', async () => {
    const noSymbols = { ...validRefresh, status: 'no_symbols', job_ids: [], symbol_count: 0,
      data_cutoff: null, timeframe: null, feed: 'IEX' }
    const sessionUnavailable = { ...validRefresh, status: 'unavailable', job_ids: [] }
    for (const payload of [noSymbols, sessionUnavailable]) {
      const fetchImpl = vi.fn(async () => jsonResponse(payload, 202))
      await expect(refreshWatchlistMarketData({
        adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl,
      })).resolves.toMatchObject({ status: payload.status, jobIds: [] })
    }
  })

  it.each([
    ['queued without job IDs', { job_ids: [] }],
    ['queued without symbols', { symbol_count: 0 }],
    ['queued without cutoff', { data_cutoff: null }],
    ['queued without timeframe', { timeframe: null }],
    ['queued without IEX feed', { feed: null }],
    ['already queued without job IDs', { status: 'already_queued', job_ids: [] }],
    ['already queued without symbols', { status: 'already_queued', symbol_count: 0 }],
    ['no symbols with positive count', { status: 'no_symbols', job_ids: [], symbol_count: 1,
      data_cutoff: null, timeframe: null }],
    ['no symbols with job IDs', { status: 'no_symbols', symbol_count: 0,
      data_cutoff: null, timeframe: null }],
    ['no symbols with cutoff', { status: 'no_symbols', job_ids: [], symbol_count: 0,
      timeframe: null }],
    ['no symbols with timeframe', { status: 'no_symbols', job_ids: [], symbol_count: 0,
      data_cutoff: null }],
    ['no symbols without IEX feed', { status: 'no_symbols', job_ids: [], symbol_count: 0,
      data_cutoff: null, timeframe: null, feed: null }],
    ['unavailable with job IDs', { status: 'unavailable' }],
    ['unavailable with partial session metadata', { status: 'unavailable', job_ids: [],
      data_cutoff: null }],
  ])('rejects contradictory %s response', async (_label, patch) => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ...validRefresh, ...patch }, 202))
    await expect(refreshWatchlistMarketData({
      adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl,
    })).rejects.toMatchObject({ kind: 'contract', message: 'Watchlist API returned an invalid refresh response' })
  })

  it('refuses to send the operator request without a server-only token', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(validRefresh, 202))
    await expect(refreshWatchlistMarketData({
      baseUrl: 'http://api.test', fetchImpl,
    })).rejects.toMatchObject({ kind: 'contract', message: 'Watchlist API authorization is unavailable' })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it.each([
    ['naive requested_at', { requested_at: '2026-10-05T12:30:00' }],
    ['naive data_cutoff', { data_cutoff: '2026-10-02T16:00:00' }],
    ['unknown status', { status: 'completed' }],
    ['unknown timeframe', { timeframe: '5Min' }],
    ['unknown feed', { feed: 'SIP' }],
    ['invalid UUID', { job_ids: ['not-a-uuid'] }],
    ['invalid count', { symbol_count: -1 }],
    ['missing message', { message: undefined }],
    ['extra field', { upstream_secret: 'private' }],
  ])('rejects %s as an invalid contract', async (_label, patch) => {
    const fetchImpl = vi.fn(async () => jsonResponse({ ...validRefresh, ...patch }, 202))
    await expect(refreshWatchlistMarketData({
      adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl,
    })).rejects.toMatchObject({ kind: 'contract', message: 'Watchlist API returned an invalid refresh response' })
  })

  it('requires HTTP 202 even if another 2xx response has a valid body', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(validRefresh, 200))
    await expect(refreshWatchlistMarketData({
      adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl,
    })).rejects.toMatchObject({ kind: 'contract', status: 200 })
  })

  it.each([403, 409, 503])('classifies HTTP %i without exposing upstream content', async (status) => {
    const fetchImpl = vi.fn(async () => new Response('secret upstream diagnostic', { status }))
    const error = await refreshWatchlistMarketData({
      adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl,
    }).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(WatchlistApiError)
    expect(error).toMatchObject({ kind: 'response', status })
    expect((error as Error).message).not.toContain('secret upstream diagnostic')
    expect((error as Error).message).not.toContain('server-secret')
  })

  it('classifies network failure without leaking credentials or a provider error', async () => {
    const fetchImpl = vi.fn(async () => { throw new Error('server-secret private provider detail') })
    await expect(refreshWatchlistMarketData({
      adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl,
    })).rejects.toMatchObject({ kind: 'unavailable', message: 'Watchlist API is unavailable' })
  })

  it('aborts a refresh request after its timeout', async () => {
    vi.useFakeTimers()
    const fetchImpl = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }))
    const operation = refreshWatchlistMarketData({
      adminToken: 'server-secret', baseUrl: 'http://api.test', fetchImpl, timeoutMs: 10,
    })
    const assertion = expect(operation).rejects.toMatchObject({ kind: 'unavailable' })
    await vi.advanceTimersByTimeAsync(10)
    await assertion
  })
})
