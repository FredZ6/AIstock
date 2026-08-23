import { describe, expect, it } from 'vitest'

import { parseWatchlistRows } from '../lib/watchlist-contract'

const validRow = {
  symbol: 'NVDA',
  daily_research: true,
  intraday_monitoring: false,
  thresholds: { return_5m: '0.025' },
  created_at: '2026-08-23T00:00:00+00:00',
  updated_at: '2026-08-23T00:05:00+00:00',
}

describe('watchlist API contract', () => {
  it('maps persisted configuration without fabricating enrichment', () => {
    expect(parseWatchlistRows([validRow])).toEqual([
      {
        symbol: 'NVDA',
        dailyResearch: true,
        intradayMonitoring: false,
        alertThreshold: '0.025',
        createdAt: '2026-08-23T00:00:00+00:00',
        updatedAt: '2026-08-23T00:05:00+00:00',
        enrichment: {
          kind: 'unavailable',
          missing: ['market', 'research', 'earnings', 'data-quality'],
        },
      },
    ])
  })

  it('maps an absent return threshold to null', () => {
    expect(parseWatchlistRows([{ ...validRow, thresholds: {} }])[0]?.alertThreshold).toBeNull()
  })

  it.each([
    ['a malformed symbol', { ...validRow, symbol: 'nvda!' }],
    ['a naive created timestamp', { ...validRow, created_at: '2026-08-23T00:00:00' }],
    ['a naive updated timestamp', { ...validRow, updated_at: '2026-08-23T00:05:00' }],
    ['a non-boolean daily research flag', { ...validRow, daily_research: 'true' }],
    ['a non-boolean intraday flag', { ...validRow, intraday_monitoring: 1 }],
    ['non-object thresholds', { ...validRow, thresholds: [] }],
    ['a non-string threshold', { ...validRow, thresholds: { return_5m: 0.025 } }],
    ['a non-decimal threshold', { ...validRow, thresholds: { return_5m: 'two percent' } }],
    [
      'a non-string secondary threshold',
      { ...validRow, thresholds: { return_5m: '0.025', volume_ratio: 2 } },
    ],
  ])('rejects %s', (_label, row) => {
    expect(() => parseWatchlistRows([row])).toThrow()
  })

  it('rejects a non-list response', () => {
    expect(() => parseWatchlistRows({ rows: [validRow] })).toThrow('watchlist must be an array')
  })
})
