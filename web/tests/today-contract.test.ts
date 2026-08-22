import { describe, expect, it } from 'vitest'

import { parseTodaySnapshot } from '../lib/api'

const validSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  mode: 'fixture',
  marketRegime: {
    label: 'RISK_ON',
    qqqTrend: '0.052',
    qqqVolatility: '0.181',
    soxxRelativeStrength: '0.024',
    vix: '18.2',
    algorithmVersion: 'market-regime-v1',
  },
  portfolio: {
    nav: '100425.18',
    currency: 'USD',
    dayReturn: '0.0042',
    drawdown: '-0.0180',
    performanceHistory: [
      { time: '2026-08-20T20:00:00Z', nav: '100005.16', cumulativeReturn: '0.0000516', drawdown: '-0.0221' },
      { time: '2026-08-21T20:00:00Z', nav: '100425.18', cumulativeReturn: '0.0042518', drawdown: '-0.0180' },
    ],
    benchmarks: {
      cash: '0.0000',
      qqq: '0.0038',
      equalWeight: '0.0031',
      momentum: '0.0045',
    },
  },
  watchlist: [
    {
      symbol: 'NVDA',
      price: '129.84',
      dailyReturn: '0.0214',
      researchOpinion: 'BULLISH',
      portfolioAction: 'HOLD',
      dataQuality: {
        freshness: 'FRESH',
        coverage: '0.94',
        provider: 'fixture-market',
        delaySeconds: '0',
        conflict: false,
      },
    },
  ],
  alerts: [
    {
      id: 'a1000000-0000-4000-8000-000000000001',
      symbol: 'NVDA',
      severity: 'HIGH',
      materiality: '0.82',
      summary: 'Volume breakout crossed the active thesis review threshold.',
      reviewAction: 'Review thesis invalidation conditions',
      eventTime: '2026-08-21T19:45:00Z',
    },
  ],
  providers: [
    { id: 'sec', label: 'SEC', status: 'HEALTHY', mode: 'fixture' },
    { id: 'options', label: 'Options', status: 'DEGRADED', mode: 'fixture' },
  ],
  activeRun: {
    id: 'b1000000-0000-4000-8000-000000000001',
    label: 'Daily research · NVDA',
    status: 'RUNNING',
    completedSteps: 6,
    totalSteps: 11,
  },
} as const

describe('parseTodaySnapshot', () => {
  it('accepts the locked Today contract without converting Decimal facts to numbers', () => {
    const snapshot = parseTodaySnapshot(validSnapshot)

    expect(snapshot.portfolio.nav).toBe('100425.18')
    expect(snapshot.portfolio.performanceHistory.at(-1)?.nav).toBe('100425.18')
    expect(snapshot.watchlist[0]?.dataQuality).toEqual({
      freshness: 'FRESH',
      coverage: '0.94',
      provider: 'fixture-market',
      delaySeconds: '0',
      conflict: false,
    })
  })

  it('rejects a naive data cutoff', () => {
    expect(() => parseTodaySnapshot({ ...validSnapshot, asOf: '2026-08-21T20:00:00' })).toThrow(
      'asOf must include a timezone',
    )
  })

  it('rejects binary numeric money at the UI boundary', () => {
    expect(() =>
      parseTodaySnapshot({
        ...validSnapshot,
        portfolio: { ...validSnapshot.portfolio, nav: 100425.18 },
      }),
    ).toThrow('portfolio.nav must be a Decimal string')
  })

  it('rejects naive timestamps and numeric values in portfolio history', () => {
    expect(() =>
      parseTodaySnapshot({
        ...validSnapshot,
        portfolio: {
          ...validSnapshot.portfolio,
          performanceHistory: [
            { ...validSnapshot.portfolio.performanceHistory[0], time: '2026-08-20T20:00:00' },
          ],
        },
      }),
    ).toThrow('portfolio.performanceHistory[0].time must include a timezone')

    expect(() =>
      parseTodaySnapshot({
        ...validSnapshot,
        portfolio: {
          ...validSnapshot.portfolio,
          performanceHistory: [
            { ...validSnapshot.portfolio.performanceHistory[0], nav: 100005.16 },
          ],
        },
      }),
    ).toThrow('portfolio.performanceHistory[0].nav must be a Decimal string')
  })

  it('keeps ResearchOpinion and PortfolioAction as independent enums', () => {
    expect(() =>
      parseTodaySnapshot({
        ...validSnapshot,
        watchlist: [{ ...validSnapshot.watchlist[0], researchOpinion: 'ENTER' }],
      }),
    ).toThrow('watchlist[0].researchOpinion is invalid')
  })
})
