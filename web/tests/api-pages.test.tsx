import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ApiPortfolioPage, ApiResearchPage, ApiTodayPage, ApiWeeklyReviewPage } from '../components/live/api-pages'

const quote = {
  availableAt: '2026-08-29T09:20:00Z',
  close: '217.545',
  coverage: 'IEX' as const,
  eventTime: '2026-08-28T04:00:00Z',
  provider: 'ALPACA',
  symbol: 'NVDA',
}
const health = {
  mode: 'paper' as const,
  providers: {
    alpaca: { configured: true, coverage: 'IEX', mode: 'read_only' as const, status: 'SUCCESS' as const },
    sec: { configured: false, coverage: null, mode: 'unavailable' as const },
  },
}
const emptyPortfolio = {
  cash: null,
  cashLedger: [],
  configuration: { currency: 'USD' as const, id: 'portfolio-1', initialCash: '100000', name: 'default-paper' },
  fills: [],
  initializedAt: null,
  latestNav: null,
  orders: [],
  performanceHistory: [],
  positions: [],
  riskDecisions: [],
  status: 'EMPTY' as const,
  trading: 'paper_only' as const,
}

describe('API mode pages', () => {
  it('shows real Today facts and explicit degraded domains without a Fixture notice', () => {
    render(<ApiTodayPage asOf="2026-08-29T09:30:00Z" health={health} portfolio={emptyPortfolio} quotes={[quote]} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    expect(screen.getByText(/ALPACA · IEX/)).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Some decision facts are unavailable' })).toHaveTextContent('No Fixture data was substituted')
    expect(screen.queryByText('Fixture Mode')).not.toBeInTheDocument()
  })

  it('keeps current quote visible when persisted research is empty', () => {
    render(<ApiResearchPage asOf="2026-08-29T09:30:00Z" quote={quote} records={[]} symbol="NVDA" />)

    expect(screen.getByRole('heading', { name: 'NVDA research' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Research evidence unavailable' })).toBeInTheDocument()
    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    expect(screen.queryByText(/frozen fixture/i)).not.toBeInTheDocument()
  })

  it('shows an empty persisted paper portfolio without inventing NAV or ledger facts', () => {
    render(<ApiPortfolioPage asOf="2026-08-29T09:30:00Z" portfolio={emptyPortfolio} />)

    expect(screen.getByRole('heading', { name: 'AI Portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Paper portfolio not initialized' })).toHaveTextContent('USD 100,000')
    expect(screen.getByRole('button', { name: 'Initialize USD 100,000 paper portfolio' })).toBeInTheDocument()
    expect(screen.queryByText('$100,425.18')).not.toBeInTheDocument()
  })

  it('shows initialized cash as success even before the first NAV snapshot', () => {
    render(<ApiPortfolioPage
      asOf="2026-08-29T09:30:00Z"
      portfolio={{ ...emptyPortfolio, cash: { balance: '100000', currency: 'USD' }, initializedAt: '2026-08-29T09:00:00Z', status: 'SUCCESS' }}
    />)

    expect(screen.getByText('USD 100,000.00')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Initialize USD/ })).not.toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Portfolio evidence is partial' })).toBeInTheDocument()
  })

  it('renders persisted weekly outcomes, calibration, attribution, and lessons', () => {
    render(<ApiWeeklyReviewPage asOf="2026-08-29T09:30:00Z" detail={{
      approvals: [],
      attributions: [{ category: 'TIMING_ERROR', controllable: true, id: 'a1', outcomeId: 'o1', rationale: 'Late entry.' }],
      calibration: [{ calibrationError: '0.2', confidence: '0.8', decisionId: 'd1', realizedReturn: '0.03', status: 'MATURED' }],
      lessons: [{ confidence: '0.7', id: 'l1', replayDelta: '0.1', statement: 'Wait for confirmation.', status: 'CANDIDATE' }],
      outcomes: [{ confidence: '0.8', decisionId: 'd1', id: 'o1', opinion: 'BULLISH', returns: { '1': '0.03' }, status: 'MATURED', symbol: 'NVDA' }],
      replays: [],
      review: { dataCutoff: '2026-08-21T20:00:00Z', id: 'r1', status: 'COMPLETED' },
    }} />)

    expect(screen.getByRole('heading', { name: 'Weekly Review' })).toBeInTheDocument()
    expect(screen.getByText('NVDA')).toBeInTheDocument()
    expect(screen.getByText('Late entry.')).toBeInTheDocument()
    expect(screen.getByText('Wait for confirmation.')).toBeInTheDocument()
    expect(screen.getAllByText('80.00%')).toHaveLength(2)
  })
})
