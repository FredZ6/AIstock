import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ResearchDirectoryPage } from '../components/research/research-directory-page'

const symbols = [
  { lastResearchAt: '2026-09-09T20:00:00Z', opinion: 'NEUTRAL', symbol: 'MSFT' },
  { lastResearchAt: '2026-09-10T20:00:00Z', opinion: 'BULLISH', symbol: 'NVDA' },
  { lastResearchAt: null, opinion: null, symbol: 'AAPL' },
] as const

describe('research directory', () => {
  it('selects only from the authoritative universe and orders persisted recent research', () => {
    render(<ResearchDirectoryPage mode="api" symbols={[...symbols]} />)

    const selector = screen.getByRole('combobox', { name: 'Research symbol' })
    expect(within(selector).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'AAPL', 'MSFT', 'NVDA',
    ])
    expect(screen.queryByText(/Fixture Mode/i)).not.toBeInTheDocument()
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      expect.stringContaining('NVDA'),
      expect.stringContaining('MSFT'),
    ])

    fireEvent.change(selector, { target: { value: 'MSFT' } })
    expect(screen.getByRole('link', { name: 'Open MSFT research' })).toHaveAttribute('href', '/research/MSFT')
  })

  it('explains an authoritative empty universe without inventing symbols', () => {
    render(<ResearchDirectoryPage mode="api" symbols={[]} />)

    expect(screen.getByRole('status', { name: 'No research symbols available' })).toHaveTextContent(
      'authoritative watchlist is empty',
    )
    expect(screen.queryByRole('link', { name: /Open .* research/ })).not.toBeInTheDocument()
  })

  it('keeps selectable symbols visible while disclosing failed recent-research reads', () => {
    render(<ResearchDirectoryPage mode="api" symbols={[...symbols]} unavailableSymbols={['AAPL']} />)

    expect(screen.getByRole('status', { name: 'Some recent research unavailable' })).toHaveTextContent('AAPL')
    expect(screen.getByRole('option', { name: 'AAPL' })).toBeInTheDocument()
    expect(screen.queryByText(/Fixture Mode/i)).not.toBeInTheDocument()
  })

  it('builds API-mode recents only from persisted watchlist and research reads', async () => {
    process.env.WEB_DATA_MODE = 'api'
    process.env.API_BASE_URL = 'http://127.0.0.1:8000'
    vi.doMock('../lib/server/watchlist-api', () => ({
      listWatchlist: vi.fn(async () => symbols.map((item) => ({ ...item, updatedAt: '2026-09-10T20:00:00Z' }))),
    }))
    vi.doMock('../lib/server/live-data-api', () => ({
      getStockResearch: vi.fn(async (_options, symbol: string) => {
        if (symbol === 'AAPL') throw new Error('provider unavailable')
        return { records: [{ asOf: symbols.find((item) => item.symbol === symbol)?.lastResearchAt, opinion: symbols.find((item) => item.symbol === symbol)?.opinion }] }
      }),
    }))
    vi.doMock('../lib/fixtures', () => { throw new Error('API mode imported Fixture data') })
    const { default: ResearchDirectoryRoute } = await import('../app/research/page')

    render(await ResearchDirectoryRoute())

    expect(screen.getByText('Research · API Mode')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open AAPL research' })).toHaveAttribute('href', '/research/AAPL')
    expect(screen.getByRole('status', { name: 'Some recent research unavailable' })).toHaveTextContent('AAPL')
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      expect.stringContaining('NVDA'),
      expect.stringContaining('MSFT'),
    ])
  })
})

afterEach(() => {
  vi.doUnmock('../lib/server/watchlist-api')
  vi.doUnmock('../lib/server/live-data-api')
  vi.doUnmock('../lib/fixtures')
  vi.resetModules()
  delete process.env.WEB_DATA_MODE
  delete process.env.API_BASE_URL
})
