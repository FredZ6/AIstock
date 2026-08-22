export type ResearchOpinion = 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'ABSTAIN'
export type PortfolioAction = 'ENTER' | 'ADD' | 'HOLD' | 'REDUCE' | 'EXIT' | 'NO_ACTION'

export type DataQuality = {
  conflict: boolean
  coverage: string
  delaySeconds: string
  freshness: 'FRESH' | 'STALE'
  provider: string
}

export type TodaySnapshot = {
  activeRun: {
    completedSteps: number
    id: string
    label: string
    status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
    totalSteps: number
  } | null
  alerts: Array<{
    eventTime: string
    id: string
    materiality: string
    reviewAction: string
    severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
    summary: string
    symbol: string
  }>
  asOf: string
  marketRegime: {
    algorithmVersion: string
    label: string
    qqqTrend: string
    qqqVolatility: string
    soxxRelativeStrength: string
    vix: string
  }
  mode: 'fixture' | 'paper' | 'test'
  portfolio: {
    benchmarks: {
      cash: string
      equalWeight: string
      momentum: string
      qqq: string
    }
    currency: 'USD'
    dayReturn: string
    drawdown: string
    nav: string
    performanceHistory: Array<{
      cumulativeReturn: string
      drawdown: string
      nav: string
      time: string
    }>
  }
  providers: Array<{
    id: string
    label: string
    mode: 'fixture' | 'read_only'
    status: 'HEALTHY' | 'DEGRADED' | 'UNAVAILABLE'
  }>
  watchlist: Array<{
    dailyReturn: string
    dataQuality: DataQuality
    portfolioAction: PortfolioAction
    price: string
    researchOpinion: ResearchOpinion
    symbol: string
  }>
}

type JsonRecord = Record<string, unknown>

const decimalPattern = /^-?\d+(?:\.\d+)?$/
const timezonePattern = /(Z|[+-]\d{2}:\d{2})$/

function record(value: unknown, path: string): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new TypeError(`${path} must be an object`)
  }
  return value as JsonRecord
}

function string(value: unknown, path: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new TypeError(`${path} must be a non-empty string`)
  }
  return value
}

function decimal(value: unknown, path: string): string {
  if (typeof value !== 'string' || !decimalPattern.test(value)) {
    throw new TypeError(`${path} must be a Decimal string`)
  }
  return value
}

function awareDateTime(value: unknown, path: string): string {
  const result = string(value, path)
  if (!timezonePattern.test(result) || Number.isNaN(Date.parse(result))) {
    throw new TypeError(`${path} must include a timezone`)
  }
  return result
}

function enumeration<const T extends readonly string[]>(
  value: unknown,
  values: T,
  path: string,
): T[number] {
  if (typeof value !== 'string' || !values.includes(value)) {
    throw new TypeError(`${path} is invalid`)
  }
  return value as T[number]
}

function integer(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new TypeError(`${path} must be a non-negative integer`)
  }
  return value
}

function list(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new TypeError(`${path} must be an array`)
  }
  return value
}

function parseDataQuality(value: unknown, path: string): DataQuality {
  const source = record(value, path)
  if (typeof source.conflict !== 'boolean') {
    throw new TypeError(`${path}.conflict must be boolean`)
  }
  return {
    freshness: enumeration(source.freshness, ['FRESH', 'STALE'] as const, `${path}.freshness`),
    coverage: decimal(source.coverage, `${path}.coverage`),
    provider: string(source.provider, `${path}.provider`),
    delaySeconds: decimal(source.delaySeconds, `${path}.delaySeconds`),
    conflict: source.conflict,
  }
}

export function parseTodaySnapshot(value: unknown): TodaySnapshot {
  const source = record(value, 'snapshot')
  const marketRegime = record(source.marketRegime, 'marketRegime')
  const portfolio = record(source.portfolio, 'portfolio')
  const benchmarks = record(portfolio.benchmarks, 'portfolio.benchmarks')
  const performanceHistory = list(
    portfolio.performanceHistory,
    'portfolio.performanceHistory',
  ).map((item, index) => {
    const path = `portfolio.performanceHistory[${index}]`
    const point = record(item, path)
    return {
      time: awareDateTime(point.time, `${path}.time`),
      nav: decimal(point.nav, `${path}.nav`),
      cumulativeReturn: decimal(point.cumulativeReturn, `${path}.cumulativeReturn`),
      drawdown: decimal(point.drawdown, `${path}.drawdown`),
    }
  })
  const activeRunSource = source.activeRun === null ? null : record(source.activeRun, 'activeRun')
  const activeRun = activeRunSource
    ? {
        id: string(activeRunSource.id, 'activeRun.id'),
        label: string(activeRunSource.label, 'activeRun.label'),
        status: enumeration(
          activeRunSource.status,
          ['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'] as const,
          'activeRun.status',
        ),
        completedSteps: integer(activeRunSource.completedSteps, 'activeRun.completedSteps'),
        totalSteps: integer(activeRunSource.totalSteps, 'activeRun.totalSteps'),
      }
    : null

  if (activeRun && (activeRun.totalSteps === 0 || activeRun.completedSteps > activeRun.totalSteps)) {
    throw new TypeError('activeRun progress is invalid')
  }

  return {
    asOf: awareDateTime(source.asOf, 'asOf'),
    mode: enumeration(source.mode, ['fixture', 'paper', 'test'] as const, 'mode'),
    marketRegime: {
      label: string(marketRegime.label, 'marketRegime.label'),
      qqqTrend: decimal(marketRegime.qqqTrend, 'marketRegime.qqqTrend'),
      qqqVolatility: decimal(marketRegime.qqqVolatility, 'marketRegime.qqqVolatility'),
      soxxRelativeStrength: decimal(
        marketRegime.soxxRelativeStrength,
        'marketRegime.soxxRelativeStrength',
      ),
      vix: decimal(marketRegime.vix, 'marketRegime.vix'),
      algorithmVersion: string(marketRegime.algorithmVersion, 'marketRegime.algorithmVersion'),
    },
    portfolio: {
      nav: decimal(portfolio.nav, 'portfolio.nav'),
      currency: enumeration(portfolio.currency, ['USD'] as const, 'portfolio.currency'),
      dayReturn: decimal(portfolio.dayReturn, 'portfolio.dayReturn'),
      drawdown: decimal(portfolio.drawdown, 'portfolio.drawdown'),
      performanceHistory,
      benchmarks: {
        cash: decimal(benchmarks.cash, 'portfolio.benchmarks.cash'),
        qqq: decimal(benchmarks.qqq, 'portfolio.benchmarks.qqq'),
        equalWeight: decimal(benchmarks.equalWeight, 'portfolio.benchmarks.equalWeight'),
        momentum: decimal(benchmarks.momentum, 'portfolio.benchmarks.momentum'),
      },
    },
    watchlist: list(source.watchlist, 'watchlist').map((item, index) => {
      const path = `watchlist[${index}]`
      const row = record(item, path)
      return {
        symbol: string(row.symbol, `${path}.symbol`),
        price: decimal(row.price, `${path}.price`),
        dailyReturn: decimal(row.dailyReturn, `${path}.dailyReturn`),
        researchOpinion: enumeration(
          row.researchOpinion,
          ['BULLISH', 'NEUTRAL', 'BEARISH', 'ABSTAIN'] as const,
          `${path}.researchOpinion`,
        ),
        portfolioAction: enumeration(
          row.portfolioAction,
          ['ENTER', 'ADD', 'HOLD', 'REDUCE', 'EXIT', 'NO_ACTION'] as const,
          `${path}.portfolioAction`,
        ),
        dataQuality: parseDataQuality(row.dataQuality, `${path}.dataQuality`),
      }
    }),
    alerts: list(source.alerts, 'alerts').map((item, index) => {
      const path = `alerts[${index}]`
      const row = record(item, path)
      return {
        id: string(row.id, `${path}.id`),
        symbol: string(row.symbol, `${path}.symbol`),
        severity: enumeration(
          row.severity,
          ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const,
          `${path}.severity`,
        ),
        materiality: decimal(row.materiality, `${path}.materiality`),
        summary: string(row.summary, `${path}.summary`),
        reviewAction: string(row.reviewAction, `${path}.reviewAction`),
        eventTime: awareDateTime(row.eventTime, `${path}.eventTime`),
      }
    }),
    providers: list(source.providers, 'providers').map((item, index) => {
      const path = `providers[${index}]`
      const row = record(item, path)
      return {
        id: string(row.id, `${path}.id`),
        label: string(row.label, `${path}.label`),
        status: enumeration(
          row.status,
          ['HEALTHY', 'DEGRADED', 'UNAVAILABLE'] as const,
          `${path}.status`,
        ),
        mode: enumeration(row.mode, ['fixture', 'read_only'] as const, `${path}.mode`),
      }
    }),
    activeRun,
  }
}

export const fixtureTodaySnapshot = parseTodaySnapshot({
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
      { time: '2026-07-25T20:00:00Z', nav: '102265.97', cumulativeReturn: '0.0226597', drawdown: '0' },
      { time: '2026-08-01T20:00:00Z', nav: '101360.00', cumulativeReturn: '0.0136', drawdown: '-0.0089' },
      { time: '2026-08-08T20:00:00Z', nav: '101620.00', cumulativeReturn: '0.0162', drawdown: '-0.0063' },
      { time: '2026-08-15T20:00:00Z', nav: '100780.00', cumulativeReturn: '0.0078', drawdown: '-0.0145' },
      { time: '2026-08-18T20:00:00Z', nav: '100240.00', cumulativeReturn: '0.0024', drawdown: '-0.0198' },
      { time: '2026-08-20T20:00:00Z', nav: '100005.16', cumulativeReturn: '0.0000516', drawdown: '-0.0221' },
      { time: '2026-08-21T20:00:00Z', nav: '100425.18', cumulativeReturn: '0.0042518', drawdown: '-0.0180' },
    ],
    benchmarks: { cash: '0', qqq: '0.0038', equalWeight: '0.0031', momentum: '0.0045' },
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
    {
      symbol: 'MSFT',
      price: '507.24',
      dailyReturn: '-0.0036',
      researchOpinion: 'NEUTRAL',
      portfolioAction: 'NO_ACTION',
      dataQuality: {
        freshness: 'STALE',
        coverage: '0.71',
        provider: 'fixture-market',
        delaySeconds: '900',
        conflict: true,
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
    { id: 'market', label: 'Market', status: 'HEALTHY', mode: 'fixture' },
    { id: 'options', label: 'Options', status: 'DEGRADED', mode: 'fixture' },
  ],
  activeRun: {
    id: 'b1000000-0000-4000-8000-000000000001',
    label: 'Daily research · NVDA',
    status: 'RUNNING',
    completedSteps: 6,
    totalSteps: 11,
  },
})
