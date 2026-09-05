import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AlertsPage } from '../components/alerts/alerts-page'
import { EvalAdminPage } from '../components/eval/eval-admin-page'
import { WeeklyReviewPage } from '../components/learning/weekly-review-page'
import { PortfolioPage } from '../components/portfolio/portfolio-page'
import { PerformanceChart } from '../components/portfolio/performance-chart'
import {
  fixtureAlertsSnapshot,
  fixtureEvalAdminSnapshot,
  fixturePortfolioSnapshot,
  fixtureWeeklyReviewSnapshot,
} from '../lib/fixtures'

describe('portfolio and review pages', () => {
  it('supports roving keyboard tabs linked to the performance panel', () => {
    render(<PerformanceChart snapshot={fixturePortfolioSnapshot} />)
    const tabs = screen.getAllByRole('tab')
    tabs[0].focus()
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(tabs[1]).toHaveFocus()
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[0]).toHaveAttribute('tabindex', '-1')
    const panel = screen.getByRole('tabpanel')
    expect(tabs[1]).toHaveAttribute('aria-controls', panel.id)
    expect(panel).toHaveAttribute('aria-labelledby', tabs[1].id)
    fireEvent.keyDown(tabs[1], { key: 'End' })
    expect(tabs[2]).toHaveFocus()
    fireEvent.keyDown(tabs[2], { key: 'ArrowRight' })
    expect(tabs[0]).toHaveFocus()
    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' })
    expect(tabs[2]).toHaveFocus()
    fireEvent.keyDown(tabs[2], { key: 'Home' })
    expect(tabs[0]).toHaveFocus()
  })

  it('normalizes monetary chart coordinates without binary floating-point loss', () => {
    const snapshot = {
      ...fixturePortfolioSnapshot,
      asOf: '2026-08-21T20:00:00Z',
      performanceHistory: [
        { time: '2026-08-19T20:00:00Z', nav: '10000000000000000.01', cumulativeReturn: '0', drawdown: '0' },
        { time: '2026-08-20T20:00:00Z', nav: '10000000000000000.02', cumulativeReturn: '0', drawdown: '0' },
        { time: '2026-08-21T20:00:00Z', nav: '10000000000000000.03', cumulativeReturn: '0', drawdown: '0' },
      ],
    }

    const { container } = render(<PerformanceChart snapshot={snapshot} />)

    expect(container.querySelector('.chart-line')).toHaveAttribute(
      'd',
      'M 0.0 230.0 L 500.0 135.0 L 1000.0 40.0',
    )
  })

  it('renders an auditable paper portfolio with cash baseline and deterministic execution facts', () => {
    render(<PortfolioPage snapshot={fixturePortfolioSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'AI Portfolio' })).toBeInTheDocument()
    expect(screen.getAllByText(/Paper Trading/i).length).toBeGreaterThan(0)
    expect(screen.getByText('USD 100,425.18')).toBeInTheDocument()
    const performance = screen.getByRole('figure', { name: 'Portfolio performance' })
    expect(within(performance).getByRole('tab', { name: 'Net asset value' })).toHaveAttribute('aria-selected', 'true')
    expect(within(performance).getByRole('img', { name: /Net asset value history/i })).toBeInTheDocument()
    expect(within(performance).getByText(/Frozen synthetic performance history/i)).toBeInTheDocument()
    fireEvent.click(within(performance).getByRole('tab', { name: 'Drawdown' }))
    expect(within(performance).getByRole('tab', { name: 'Drawdown' })).toHaveAttribute('aria-selected', 'true')
    expect(within(performance).getByRole('img', { name: /Drawdown history/i })).toBeInTheDocument()
    fireEvent.click(within(performance).getByRole('button', { name: 'Last 7 days' }))
    expect(within(performance).getByRole('button', { name: 'Last 7 days' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('figure', { name: /Benchmark comparison/ })).toBeInTheDocument()
    for (const benchmark of ['Cash', 'QQQ', 'Equal weight', 'Momentum']) {
      expect(screen.getByText(benchmark)).toBeInTheDocument()
    }
    const positions = screen.getByRole('table', { name: 'Paper portfolio positions' })
    expect(within(positions).getByText('NVDA')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'NVDA current market chart' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'MSFT current market chart' })).toBeInTheDocument()
    expect(screen.getByText(/next eligible bar/i)).toBeInTheDocument()
    expect(screen.getByText('execution-v1')).toBeInTheDocument()
    expect(screen.getByText(/balanced ledger/i)).toBeInTheDocument()
    expect(screen.getAllByText('USD 74,699.58').length).toBeGreaterThan(0)
    expect(within(positions).getByRole('columnheader', { name: 'Unrealized P&L' })).toBeInTheDocument()
    const risks = screen.getByRole('table', { name: 'Risk decisions' })
    expect(within(risks).getByText('REJECTED')).toBeInTheDocument()
    expect(within(risks).getByText(/position concentration limit/i)).toBeInTheDocument()
    expect(within(screen.getByRole('table', { name: 'Paper fills' })).getByText('fill-nvda-001')).toBeInTheDocument()
    expect(within(screen.getByRole('table', { name: 'Paper fills' })).getByText('fill-msft-001')).toBeInTheDocument()
    const cashLedger = screen.getByRole('table', { name: 'Cash ledger' })
    expect(within(cashLedger).getByText('ledger-opening-001')).toBeInTheDocument()
    expect(within(cashLedger).getByText('ledger-buy-nvda-001')).toBeInTheDocument()
    expect(within(cashLedger).getByText('ledger-buy-msft-001')).toBeInTheDocument()
    expect(within(cashLedger).getAllByText('USD 74,699.58')).toHaveLength(1)
  })

  it('renders deterministic alerts with thesis linkage and visible explanation failure', () => {
    render(<AlertsPage snapshot={fixtureAlertsSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
    expect(screen.getAllByText('HIGH').length).toBeGreaterThan(0)
    expect(screen.getByText(/materiality 82%/i)).toBeInTheDocument()
    expect(screen.getAllByText('thesis-nvda-v3').length).toBeGreaterThan(0)
    expect(screen.getByText('evidence-volume-breakout')).toBeInTheDocument()
    expect(screen.getByText('invalidation-nvda-volume-001')).toBeInTheDocument()
    expect(screen.getByText(/Explanation unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/deterministic alert remains valid/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Acknowledge alert alert-nvda-volume-001' })).toBeDisabled()
    for (const category of ['PRICE', 'VOLUME', 'OPTIONS', 'EARNINGS', 'NEWS', 'ANALYST_TARGET', 'PORTFOLIO_RISK']) {
      expect(screen.getByText(category)).toBeInTheDocument()
    }
  })

  it('makes weekly lesson approval consequences and replay evidence explicit', () => {
    render(<WeeklyReviewPage snapshot={fixtureWeeklyReviewSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Weekly Review' })).toBeInTheDocument()
    expect(screen.getByText(/Outcome attribution/i)).toBeInTheDocument()
    expect(screen.getByText(/Timing error/i)).toBeInTheDocument()
    expect(screen.getByText('lesson-risk-regime-001')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Point-in-time replay' })).toBeInTheDocument()
    expect(screen.getByText(/human approval was recorded/i)).toBeInTheDocument()
    expect(screen.getByText(/candidate remains inactive/i)).toBeInTheDocument()
    expect(screen.getByText(/automatic activation is disabled/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve candidate lesson' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject candidate lesson' })).toBeDisabled()
    expect(screen.getByRole('heading', { name: 'Thesis outcomes' })).toBeInTheDocument()
    expect(screen.getByText('HIT')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Confidence calibration' })).toBeInTheDocument()
    expect(screen.getByText(/70–79% confidence/i)).toBeInTheDocument()
  })

  it('keeps Eval and policy administration read-only in fixture mode', () => {
    render(<EvalAdminPage snapshot={fixtureEvalAdminSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Eval & Admin' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Offline evaluation report unavailable' })).toBeInTheDocument()
    expect(screen.getByText(/No metric is substituted or invented/i)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Pinned policy versions' })).toBeInTheDocument()
    expect(screen.getByText('confidence-v1')).toBeInTheDocument()
    expect(screen.getAllByText(/human authorization required/i)).toHaveLength(4)
    expect(screen.getAllByText(/automatic activation is disabled/i)).toHaveLength(4)
    expect(screen.queryByText(/Live Broker/i)).not.toBeInTheDocument()
  })
})
