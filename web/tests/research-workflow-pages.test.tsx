import { render, screen, within } from '@testing-library/react'
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
  it('renders a semantic watchlist with separate research and portfolio decisions', () => {
    render(<WatchlistPage snapshot={fixtureWatchlistSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Watchlist' })).toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Research watchlist' })
    expect(within(table).getByRole('columnheader', { name: 'Research opinion' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Portfolio action' })).toBeInTheDocument()
    expect(within(table).getByText('ABSTAIN')).toBeInTheDocument()
    expect(within(table).getAllByText('NO_ACTION')).toHaveLength(2)
    expect(within(table).getAllByText(/coverage/).length).toBeGreaterThan(0)
    expect(screen.getByText(/5 of 20 symbols/i)).toBeInTheDocument()
  })

  it('traces a thesis statement through claim, evidence, tool call, provider, and timestamp', () => {
    render(<ResearchPage snapshot={fixtureResearchSnapshot} />)

    expect(screen.getByRole('heading', { level: 1, name: /NVDA research/i })).toBeInTheDocument()
    expect(screen.getByText('BULLISH')).toBeInTheDocument()
    expect(screen.getByText('HOLD')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Investment thesis' })).toBeInTheDocument()
    expect(screen.getByText(/CONTRADICTS/)).toBeInTheDocument()
    expect(screen.getByText(/UNAVAILABLE/)).toBeInTheDocument()
    expect(screen.getByText('claim-nvda-demand')).toBeInTheDocument()
    expect(screen.getByText('evidence-sec-revenue')).toBeInTheDocument()
    expect(screen.getByText('tool-sec-companyfacts')).toBeInTheDocument()
    expect(screen.getByText(/SEC Company Facts/)).toBeInTheDocument()
    expect(screen.getAllByText(/New York/).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Decision diff' })).toBeInTheDocument()
    expect(screen.getByText(/confidence changed/i)).toBeInTheDocument()
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
    const trace = screen.getByRole('list', { name: 'Durable run events' })
    expect(within(trace).getAllByRole('listitem')).toHaveLength(fixtureRunTrace.events.length)
    expect(screen.getByText(/Last-Event-ID/i)).toBeInTheDocument()
  })
})
