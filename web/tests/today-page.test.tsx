import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TodayPage } from '../components/today-page'
import { parseTodaySnapshot } from '../lib/api'

const snapshot = parseTodaySnapshot({
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
})

describe('TodayPage', () => {
  it('leads with point-in-time market context, portfolio facts, and all four benchmarks', () => {
    render(<TodayPage snapshot={snapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
    expect(screen.getByText('RISK_ON')).toBeInTheDocument()
    expect(screen.getByText('market-regime-v1')).toBeInTheDocument()
    expect(screen.getByText(/100,425\.18/)).toBeInTheDocument()
    expect(screen.getByText('+0.42%')).toBeInTheDocument()
    expect(screen.getByText('-1.80%')).toBeInTheDocument()
    for (const benchmark of ['Cash', 'QQQ', 'Equal weight', 'Momentum']) {
      expect(screen.getByText(benchmark)).toBeInTheDocument()
    }
    expect(screen.getByText(/New York/i)).toBeInTheDocument()
    expect(screen.getByText(/Shanghai/i)).toBeInTheDocument()
  })

  it('keeps opinion, action, and raw data-quality dimensions distinct in a semantic table', () => {
    render(<TodayPage snapshot={snapshot} />)

    const table = screen.getByRole('table', { name: 'Watchlist signals' })
    for (const heading of ['Symbol', 'Price', 'Day', 'Research opinion', 'Portfolio action', 'Data quality']) {
      expect(within(table).getByRole('columnheader', { name: heading })).toBeInTheDocument()
    }
    expect(within(table).getByRole('link', { name: 'NVDA' })).toHaveAttribute('href', '/research/NVDA')
    expect(within(table).getByText('BULLISH')).toBeInTheDocument()
    expect(within(table).getByText('HOLD')).toBeInTheDocument()
    expect(within(table).getByText(/94% coverage/)).toBeInTheDocument()
    expect(within(table).getByText(/fixture-market/)).toBeInTheDocument()
    expect(within(table).getByText(/0s delay/)).toBeInTheDocument()
    expect(within(table).getByText(/No conflict/)).toBeInTheDocument()
  })

  it('names degraded providers while preserving alerts and durable run progress', () => {
    render(<TodayPage snapshot={snapshot} />)

    expect(screen.getByRole('status', { name: 'Provider coverage degraded' })).toHaveTextContent(
      'Options',
    )
    expect(screen.getByText('Volume breakout crossed the active thesis review threshold.')).toBeInTheDocument()
    expect(screen.getByText('Review thesis invalidation conditions')).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
    const progress = screen.getByRole('progressbar', { name: 'Daily research · NVDA' })
    expect(progress).toHaveAttribute('value', '6')
    expect(progress).toHaveAttribute('max', '11')
    expect(screen.getByText('6 of 11 steps')).toBeInTheDocument()
  })
})
