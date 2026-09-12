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
    const list = screen.getByRole('list', { name: 'Ranked research watchlist' })
    expect(within(list).getByText('ABSTAIN')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'TSLA settings' })).getByText('NO_ACTION')).toBeInTheDocument()
    expect(within(list).getAllByText(/coverage/).length).toBeGreaterThan(0)
    expect(screen.getByText(/5 of 20 symbols/i)).toBeInTheDocument()
    const currentMarket = screen.getByRole('region', { name: 'Current market reference' })
    await waitFor(() => expect(currentMarket.querySelector('script')?.textContent).toContain('NASDAQ:NVDA'))
    expect(currentMarket.querySelector('script')?.textContent).toContain('NASDAQ:MSFT')
  })

  it('supports a fixture-session watchlist draft with schedules, thresholds, and earnings dates', () => {
    render(<WatchlistPage snapshot={fixtureWatchlistSnapshot} />)

    expect(screen.getByRole('heading', { name: 'Watchlist controls' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'NVDA daily research' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'NVDA intraday monitoring' })).toBeChecked()
    expect(screen.getByRole('textbox', { name: 'NVDA alert threshold' })).toHaveValue('0.025')
    const nvdaSettings = screen.getByRole('region', { name: 'NVDA settings' })
    expect(within(nvdaSettings).getByText(/Next earnings:/)).toBeInTheDocument()
    expect(within(nvdaSettings).getByText('Aug 27, 2026')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: 'Add symbol' }), {
      target: { value: 'goog' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add to watchlist' }))
    expect(within(screen.getByRole('list', { name: 'Ranked research watchlist' }))
      .getByRole('link', { name: 'GOOG' })).toBeInTheDocument()
    expect(screen.getByText('6 of 20 symbols')).toBeInTheDocument()
    expect(screen.getByText(/session-only configuration draft/i)).toBeInTheDocument()
  })

  it('traces a dashboard conclusion through report, claim, evidence, tool call, provider, and timestamp', async () => {
    render(<ResearchPage snapshot={fixtureResearchSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: /NVDA research/i })).toBeInTheDocument()
    const overview = screen.getByRole('region', { name: 'NVDA current market overview' })
    await waitFor(() => expect(overview.querySelector('script')).toHaveAttribute(
      'src',
      'https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js',
    ))
    expect(overview.querySelector('script')?.textContent).toContain('NASDAQ:NVDA|1D')
    expect(overview.querySelector('.tradingview-widget-container')).toHaveAttribute('tabindex', '0')
    expect(overview.querySelector('.tradingview-widget-container')).toHaveAttribute('role', 'region')
    expect(overview.querySelector('.tradingview-widget-container')).toHaveAttribute(
      'aria-label',
      'Scrollable NVDA TradingView overview',
    )
    expect(screen.getByText(/not decision-time evidence/i)).toBeInTheDocument()
    expect(screen.getAllByText('BULLISH').length).toBeGreaterThan(0)
    expect(screen.getAllByText('HOLD').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Investment thesis' })).toBeInTheDocument()
    expect(screen.getByText('report-nvda-v3')).toBeInTheDocument()
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

  it('orders the research conclusion, current market context, and point-in-time evidence explicitly', () => {
    render(<ResearchPage snapshot={fixtureResearchSnapshot} />)

    const main = screen.getByRole('main')
    const conclusion = screen.getByRole('region', { name: 'NVDA research conclusion' })
    const currentMarket = screen.getByRole('region', { name: 'NVDA current market overview' })
    const pitEvidence = screen.getByRole('region', { name: 'Point-in-time research evidence' })
    expect(conclusion).toHaveTextContent('BULLISH')
    expect(conclusion).toHaveTextContent('74.00%')
    expect(conclusion).toHaveTextContent('Evidence freshness')
    expect(main.contains(conclusion)).toBe(true)
    expect(conclusion.compareDocumentPosition(currentMarket)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(currentMarket.compareDocumentPosition(pitEvidence)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('exposes each research question as a labelled region', () => {
    render(<ResearchPage snapshot={fixtureResearchSnapshot} />)

    for (const name of [
      'Fundamentals',
      'Earnings',
      'News',
      'Options',
      'Analyst targets',
      'Evidence gaps',
      'Decision history',
    ]) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument()
    }
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

  it('summarizes run progress and cutoff before the verbose durable event list', () => {
    render(<RunTracePage snapshot={fixtureRunTrace} />)

    const summary = screen.getByRole('region', { name: 'Run operations summary' })
    const events = screen.getByRole('region', { name: 'Durable event trace' })
    expect(summary).toHaveTextContent('RUNNING')
    expect(within(summary).getByText('Elapsed').parentElement).toHaveTextContent('28,000 ms')
    expect(within(summary).getByText('Current step').parentElement).toHaveTextContent('Citation verifier running')
    expect(within(summary).getByText('Retries').parentElement).toHaveTextContent('1')
    expect(within(summary).getByText('Degradations').parentElement).toHaveTextContent('1')
    expect(within(summary).getByText('Checkpoints').parentElement).toHaveTextContent('1')
    expect(summary).toHaveTextContent('Data cutoff')
    expect(summary.querySelector('time')).toHaveAttribute('datetime', fixtureRunTrace.asOf)
    expect(summary.compareDocumentPosition(events) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
