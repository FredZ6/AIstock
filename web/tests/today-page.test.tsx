import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TodayPage } from '../components/today-page'
import { PerformanceChart } from '../components/portfolio/performance-chart'
import { fixtureTodaySnapshot } from '../lib/api'

const snapshot = fixtureTodaySnapshot

function activateButtonWithKeyboard(button: HTMLElement) {
  button.focus()
  fireEvent.keyDown(button, { key: 'Enter' })
  fireEvent.click(button, { detail: 0 })
  fireEvent.keyUp(button, { key: 'Enter' })
}

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

  it('switches the compact portfolio chart between one persisted metric at a time', () => {
    render(<TodayPage snapshot={snapshot} />)

    const portfolio = screen.getByRole('figure', { name: 'Paper portfolio performance' })
    const tabs = within(portfolio).getByRole('tablist', { name: 'Performance metric' })
    const nav = within(tabs).getByRole('tab', { name: 'Net asset value' })
    const dayReturn = within(tabs).getByRole('tab', { name: 'Day return' })
    const drawdown = within(tabs).getByRole('tab', { name: 'Current drawdown' })

    expect(nav).toHaveAttribute('aria-selected', 'true')
    expect(dayReturn).toHaveAttribute('aria-selected', 'false')
    expect(drawdown).toHaveAttribute('aria-selected', 'false')
    expect(within(portfolio).getByRole('img', { name: 'Net asset value history' }))
      .toHaveProperty('parentElement.dataset.metric', 'nav')
    expect(within(portfolio).getAllByRole('img')).toHaveLength(1)

    fireEvent.click(dayReturn)
    expect(within(portfolio).getByRole('img', { name: 'Day return history' }))
      .toHaveProperty('parentElement.dataset.metric', 'dailyReturn')

    fireEvent.keyDown(dayReturn, { key: 'ArrowRight' })
    expect(drawdown).toHaveFocus()
    expect(drawdown).toHaveAttribute('aria-selected', 'true')
    expect(within(portfolio).getByRole('img', { name: 'Current drawdown history' }))
      .toHaveProperty('parentElement.dataset.metric', 'drawdown')
    expect(within(portfolio).queryByRole('tab', { name: 'Cumulative return' })).not.toBeInTheDocument()
  })

  it('does not fabricate a line when a selected metric has insufficient persisted history', () => {
    render(<PerformanceChart compact snapshot={{
      asOf: snapshot.asOf,
      currency: snapshot.portfolio.currency,
      dayReturn: snapshot.portfolio.dayReturn,
      drawdown: snapshot.portfolio.drawdown,
      nav: snapshot.portfolio.nav,
      performanceHistory: [{
        dailyReturn: null,
        drawdown: snapshot.portfolio.drawdown,
        nav: snapshot.portfolio.nav,
        time: snapshot.asOf,
      }],
    }} />)

    const portfolio = screen.getByRole('figure', { name: 'Paper portfolio performance' })
    fireEvent.click(within(portfolio).getByRole('tab', { name: 'Day return' }))

    expect(within(portfolio).getByText('Not enough persisted history for this metric.')).toBeInTheDocument()
    expect(within(portfolio).queryByRole('img', { name: 'Day return history' })).not.toBeInTheDocument()
    expect(portfolio.querySelector('.chart-line')).not.toBeInTheDocument()
  })

  it('groups market metadata inside the rounded summary surface', () => {
    render(<TodayPage snapshot={snapshot} />)

    const summary = screen.getByRole('region', { name: 'Market and portfolio summary' })
    const regime = within(summary).getByRole('region', { name: 'Market regime' })
    expect(summary).toHaveClass('surface-card')
    expect(within(summary).getByTestId('regime-metadata')).toContainElement(
      within(summary).getByText('market-regime-v1'),
    )
    expect(within(regime).getByRole('heading', { name: 'Benchmark pulse' })).toBeInTheDocument()
    for (const benchmark of ['Cash', 'QQQ', 'Equal weight', 'Momentum']) {
      expect(within(regime).getByText(benchmark)).toBeInTheDocument()
      expect(screen.getAllByText(benchmark)).toHaveLength(1)
    }
  })

  it('keeps safety context compact so decision facts lead the first viewport', () => {
    render(<TodayPage snapshot={snapshot} />)

    const heading = screen.getByRole('heading', { level: 1, name: 'Today' }).closest('header')
    expect(heading).not.toBeNull()
    expect(within(heading!).getByRole('note')).toHaveTextContent('Fixture Mode')
    expect(screen.getByRole('status', { name: 'Provider coverage degraded' })).toHaveClass(
      'state-compact',
    )
    expect(screen.getByText('1 unavailable fact').closest('details')).not.toHaveAttribute('open')
  })

  it('groups every decision-critical region into the dense desktop workspace', () => {
    render(<TodayPage snapshot={snapshot} />)

    const workspace = screen.getByRole('region', { name: 'Today decision workspace' })
    expect(workspace).toHaveClass('today-decision-workspace')
    expect(within(workspace).getByRole('region', { name: 'Portfolio overview' })).toHaveClass(
      'portfolio-overview',
    )
    expect(within(workspace).getByRole('region', { name: 'Market regime' })).toHaveClass(
      'market-regime-compact',
    )
    expect(within(workspace).getByRole('list', { name: 'Watchlist signals' })).toHaveClass(
      'market-list',
    )
    expect(within(workspace).getByRole('region', { name: 'Decision activity' })).toHaveClass(
      'decision-activity',
    )
    expect(within(workspace).getByRole('region', { name: 'Market and portfolio summary' })).toBeInTheDocument()
    expect(within(workspace).getByRole('region', { name: 'Watchlist signals' })).toBeInTheDocument()
    expect(within(workspace).getByRole('region', { name: 'Research execution' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Provider diagnostics' })).not.toHaveAttribute('open')
  })

  it('renders a non-color-only watchlist heatmap with distinct decisions and raw quality facts', () => {
    render(<TodayPage snapshot={snapshot} />)

    const heatmap = screen.getByRole('list', { name: 'Watchlist signals' })
    expect(within(heatmap).getByRole('link', { name: 'NVDA' })).toHaveAttribute('href', '/research/NVDA')
    expect(within(heatmap).getByText('+2.14%')).toBeInTheDocument()
    expect(within(heatmap).getByText('BULLISH')).toBeInTheDocument()
    expect(within(heatmap).getByText('HOLD')).toBeInTheDocument()
    expect(within(heatmap).getByText(/94% coverage/)).toBeInTheDocument()
    expect(within(heatmap).getAllByText(/fixture-market/)).toHaveLength(snapshot.watchlist.length)
    expect(within(heatmap).getByText('0s delay')).toBeInTheDocument()
    expect(within(heatmap).getByText(/No conflict/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show all/ })).not.toBeInTheDocument()
  })

  it('shows two Watchlist rows until the user expands the same list by keyboard', () => {
    const fourRowSnapshot = {
      ...snapshot,
      watchlist: [
        ...snapshot.watchlist,
        { ...snapshot.watchlist[0]!, symbol: 'AMD' },
        { ...snapshot.watchlist[1]!, symbol: 'AAPL' },
      ],
    }
    render(<TodayPage snapshot={fourRowSnapshot} />)

    const list = screen.getByRole('list', { name: 'Watchlist signals' })
    expect(within(list).getAllByRole('link')).toHaveLength(2)
    expect(within(list).getByRole('link', { name: 'NVDA' })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: 'MSFT' })).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: 'AMD' })).not.toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: 'AAPL' })).not.toBeInTheDocument()

    const showAll = screen.getByRole('button', { name: 'Show all (4)' })
    expect(showAll).toHaveAttribute('aria-expanded', 'false')
    expect(showAll).toHaveAttribute('aria-controls', list.id)

    activateButtonWithKeyboard(showAll)

    expect(screen.getByRole('list', { name: 'Watchlist signals' })).toBe(list)
    expect(within(list).getAllByRole('link')).toHaveLength(4)
    expect(within(list).getByRole('link', { name: 'AMD' })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: 'AAPL' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true')
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
