import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ApiPortfolioPage, ApiResearchPage, ApiTodayPage } from '../components/live/api-pages'

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

describe('API mode pages', () => {
  it('shows real Today facts and explicit degraded domains without a Fixture notice', () => {
    render(<ApiTodayPage asOf="2026-08-29T09:30:00Z" health={health} portfolio={{ latestNav: null, trading: 'paper_only' }} quotes={[quote]} />)

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
    render(<ApiPortfolioPage asOf="2026-08-29T09:30:00Z" portfolio={{ latestNav: null, trading: 'paper_only' }} />)

    expect(screen.getByRole('heading', { name: 'AI Portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('alert', { name: 'Portfolio facts unavailable' })).toHaveTextContent('No Fixture portfolio was substituted')
    expect(screen.queryByText('$100,425.18')).not.toBeInTheDocument()
  })
})
