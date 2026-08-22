import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ResearchPage } from '../components/research/research-page'
import { RunTracePage } from '../components/trace/run-trace-page'
import { WatchlistPage } from '../components/watchlist/watchlist-page'
import {
  fixtureResearchSnapshot,
  fixtureRunTrace,
  fixtureWatchlistSnapshot,
} from '../lib/fixtures'

describe('research workflow pages', () => {
  it('renders a semantic watchlist with separate research and portfolio decisions', async () => {
    render(<WatchlistPage snapshot={fixtureWatchlistSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Watchlist' })).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Research watchlist' })
    expect(within(table).getByRole('columnheader', { name: 'Research opinion' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Portfolio action' })).toBeInTheDocument()
    expect(within(table).getByText('ABSTAIN')).toBeInTheDocument()
    expect(within(table).getAllByText('NO_ACTION')).toHaveLength(2)
    expect(within(table).getAllByText(/coverage/).length).toBeGreaterThan(0)
    expect(screen.getByText(/5 of 20 symbols/i)).toBeInTheDocument()
    const nvdaChart = screen.getByRole('region', { name: 'NVDA current market chart' })
    await waitFor(() => expect(nvdaChart.querySelector('script')?.textContent).toContain('NASDAQ:NVDA'))
    expect(nvdaChart.querySelector('script')?.textContent).toContain('"isTransparent":false')
    expect(screen.getByRole('region', { name: 'MSFT current market chart' })).toBeInTheDocument()
  })

  it('supports a fixture-session watchlist draft with schedules, thresholds, and earnings dates', () => {
    render(<WatchlistPage snapshot={fixtureWatchlistSnapshot} />)

    expect(screen.getByRole('heading', { name: 'Watchlist controls' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'NVDA daily research' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'NVDA intraday monitoring' })).toBeChecked()
    expect(screen.getByRole('textbox', { name: 'NVDA alert threshold' })).toHaveValue('0.025')
    expect(screen.getByRole('columnheader', { name: 'Next earnings' })).toBeInTheDocument()
    expect(screen.getByText('Aug 27, 2026')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: 'Add symbol' }), {
      target: { value: 'goog' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add to watchlist' }))
    expect(screen.getByRole('rowheader', { name: 'GOOG' })).toBeInTheDocument()
    expect(screen.getByText('6 of 20 symbols')).toBeInTheDocument()
    expect(screen.getByText(/session-only configuration draft/i)).toBeInTheDocument()
  })

  it('traces a thesis statement through claim, evidence, tool call, provider, and timestamp', async () => {
    render(<ResearchPage snapshot={fixtureResearchSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: /NVDA research/i })).toBeInTheDocument()
    const overview = screen.getByRole('region', { name: 'NVDA current market overview' })
    await waitFor(() => expect(overview.querySelector('script')).toHaveAttribute(
      'src',
      'https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js',
    ))
    expect(overview.querySelector('script')?.textContent).toContain('NASDAQ:NVDA|1D')
    expect(screen.getByText(/not decision-time evidence/i)).toBeInTheDocument()
    expect(screen.getAllByText('BULLISH').length).toBeGreaterThan(0)
    expect(screen.getAllByText('HOLD').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Investment thesis' })).toBeInTheDocument()
    expect(screen.getByText(/CONTRADICTS/)).toBeInTheDocument()
    expect(screen.getAllByText(/UNAVAILABLE/).length).toBeGreaterThan(0)
    expect(screen.getByText('claim-nvda-demand')).toBeInTheDocument()
    expect(screen.getByText('evidence-sec-revenue')).toBeInTheDocument()
    expect(screen.getByText('tool-sec-companyfacts')).toBeInTheDocument()
    expect(screen.getByText(/SEC Company Facts/)).toBeInTheDocument()
    expect(screen.getAllByText(/New York/).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Decision diff' })).toBeInTheDocument()
    expect(screen.getByText(/confidence changed/i)).toBeInTheDocument()
  })

  it('covers every locked research domain and immutable decision history', () => {
    render(<ResearchPage snapshot={fixtureResearchSnapshot} />)

    for (const heading of [
      'Fundamentals',
      'Earnings',
      'News',
      'Options',
      'Analyst targets',
      'Decision history',
    ]) {
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
    }
    const history = screen.getByRole('table', { name: 'Immutable decision history' })
    expect(within(history).getByText('decision-nvda-v3')).toBeInTheDocument()
    expect(within(history).getByText('decision-nvda-v2')).toBeInTheDocument()
    expect(within(history).getByText('BULLISH')).toBeInTheDocument()
    expect(within(history).getByText('HOLD')).toBeInTheDocument()
  })

  it('shows an ordered durable run trace with budgets, retries, fallback, and checkpoints', () => {
    render(<RunTracePage snapshot={fixtureRunTrace} />)

    expect(screen.getByRole('heading', { level: 1, name: /Research run/i })).toBeInTheDocument()
    expect(screen.getByText(/6 of 10 LLM calls/i)).toBeInTheDocument()
    expect(screen.getByText(/9 of 16 tool calls/i)).toBeInTheDocument()
    expect(screen.getByText(/12,480 tokens/i)).toBeInTheDocument()
    expect(screen.getByText(/USD 0.84/i)).toBeInTheDocument()
    expect(screen.getByText(/retry 1 of 3/i)).toBeInTheDocument()
    expect(screen.getByText(/fixture fallback/i)).toBeInTheDocument()
    expect(screen.getByText(/checkpoint saved/i)).toBeInTheDocument()
    expect(screen.getByText('2,000 ms')).toBeInTheDocument()
    expect(screen.getByText('4,000 ms')).toBeInTheDocument()
    const trace = screen.getByRole('list', { name: 'Durable run events' })
    expect(within(trace).getAllByRole('listitem')).toHaveLength(fixtureRunTrace.events.length)
    expect(screen.getByText(/Last-Event-ID/i)).toBeInTheDocument()
  })
})
