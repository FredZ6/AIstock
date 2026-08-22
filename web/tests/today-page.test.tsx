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
    performanceHistory: [
      { time: '2026-08-15T20:00:00Z', nav: '100780.00', cumulativeReturn: '0.0078', drawdown: '-0.0145' },
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

  it('shows the Paper portfolio as a compact performance chart with a full-detail route', () => {
    render(<TodayPage snapshot={snapshot} />)

    const portfolio = screen.getByRole('figure', { name: 'Paper portfolio performance' })
    expect(within(portfolio).getByRole('img', { name: 'Net asset value history' })).toBeInTheDocument()
    expect(within(portfolio).getByRole('link', { name: 'Open portfolio' })).toHaveAttribute(
      'href',
      '/portfolio',
    )
    expect(within(portfolio).getByText('Frozen synthetic history')).toBeInTheDocument()
  })

  it('groups market metadata inside the rounded summary surface', () => {
    render(<TodayPage snapshot={snapshot} />)

    const summary = screen.getByRole('region', { name: 'Market and portfolio summary' })
    expect(summary).toHaveClass('surface-card')
    expect(within(summary).getByTestId('regime-metadata')).toContainElement(
      within(summary).getByText('market-regime-v1'),
    )
  })

  it('keeps safety context compact so decision facts lead the first viewport', () => {
    render(<TodayPage snapshot={snapshot} />)

    const heading = screen.getByRole('heading', { level: 1, name: 'Today' }).closest('header')
    expect(heading).not.toBeNull()
    expect(within(heading!).getByRole('note')).toHaveTextContent('Fixture Mode')
    expect(screen.getByRole('status', { name: 'Provider coverage degraded' })).toHaveClass(
      'state-compact',
    )
  })

  it('renders a non-color-only watchlist heatmap with distinct decisions and raw quality facts', () => {
    render(<TodayPage snapshot={snapshot} />)

    const heatmap = screen.getByRole('list', { name: 'Watchlist heatmap' })
    expect(within(heatmap).getByRole('link', { name: 'NVDA' })).toHaveAttribute('href', '/research/NVDA')
    expect(within(heatmap).getByText('+2.14%')).toBeInTheDocument()
    expect(within(heatmap).getByText('BULLISH')).toBeInTheDocument()
    expect(within(heatmap).getByText('HOLD')).toBeInTheDocument()
    expect(within(heatmap).getByText(/94% coverage/)).toBeInTheDocument()
    expect(within(heatmap).getByText(/fixture-market/)).toBeInTheDocument()
    expect(within(heatmap).getByText(/0s delay/)).toBeInTheDocument()
    expect(within(heatmap).getByText(/No conflict/)).toBeInTheDocument()
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
