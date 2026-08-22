import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AlertsPage } from '../components/alerts/alerts-page'
import { EvalAdminPage } from '../components/eval/eval-admin-page'
import { WeeklyReviewPage } from '../components/learning/weekly-review-page'
import { PortfolioPage } from '../components/portfolio/portfolio-page'
import {
  fixtureAlertsSnapshot,
  fixtureEvalAdminSnapshot,
  fixturePortfolioSnapshot,
  fixtureWeeklyReviewSnapshot,
} from '../lib/fixtures'

describe('portfolio and review pages', () => {
  it('renders an auditable paper portfolio with cash baseline and deterministic execution facts', () => {
    render(<PortfolioPage snapshot={fixturePortfolioSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'AI Portfolio' })).toBeInTheDocument()
    expect(screen.getAllByText(/Paper Trading/i).length).toBeGreaterThan(0)
    expect(screen.getByText('USD 100,425.18')).toBeInTheDocument()
    expect(screen.getByRole('figure', { name: /Benchmark comparison/ })).toBeInTheDocument()
    for (const benchmark of ['Cash', 'QQQ', 'Equal weight', 'Momentum']) {
      expect(screen.getByText(benchmark)).toBeInTheDocument()
    }
    const positions = screen.getByRole('table', { name: 'Paper portfolio positions' })
    expect(within(positions).getByText('NVDA')).toBeInTheDocument()
    expect(screen.getByText(/next eligible bar/i)).toBeInTheDocument()
    expect(screen.getByText('execution-v1')).toBeInTheDocument()
    expect(screen.getByText(/balanced ledger/i)).toBeInTheDocument()
  })

  it('renders deterministic alerts with thesis linkage and visible explanation failure', () => {
    render(<AlertsPage snapshot={fixtureAlertsSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
    expect(screen.getByText(/materiality 82%/i)).toBeInTheDocument()
    expect(screen.getByText('thesis-nvda-v3')).toBeInTheDocument()
    expect(screen.getByText('evidence-volume-breakout')).toBeInTheDocument()
    expect(screen.getByText(/Explanation unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/deterministic alert remains valid/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Acknowledge alert/i })).toBeDisabled()
  })

  it('makes weekly lesson approval consequences and replay evidence explicit', () => {
    render(<WeeklyReviewPage snapshot={fixtureWeeklyReviewSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Weekly Review' })).toBeInTheDocument()
    expect(screen.getByText(/Outcome attribution/i)).toBeInTheDocument()
    expect(screen.getByText(/Timing error/i)).toBeInTheDocument()
    expect(screen.getByText('lesson-risk-regime-001')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Point-in-time replay' })).toBeInTheDocument()
    expect(screen.getByText(/approval records a human decision only/i)).toBeInTheDocument()
    expect(screen.getByText(/does not activate a policy/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve candidate lesson' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject candidate lesson' })).toBeDisabled()
  })

  it('keeps Eval and policy administration read-only in fixture mode', () => {
    render(<EvalAdminPage snapshot={fixtureEvalAdminSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Eval & Admin' })).toBeInTheDocument()
    expect(screen.getByText(/Task 16 evaluation gates have not started/i)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Pinned policy versions' })).toBeInTheDocument()
    expect(screen.getByText('confidence-v1')).toBeInTheDocument()
    expect(screen.getAllByText(/human authorization required/i)).toHaveLength(4)
    expect(screen.getAllByText(/automatic activation is disabled/i)).toHaveLength(4)
    expect(screen.queryByText(/Live Broker/i)).not.toBeInTheDocument()
  })
})
