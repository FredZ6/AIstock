import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StateBoundary } from '../components/states/state-boundary'

describe('StateBoundary', () => {
  it('announces loading without presenting stale content as current', () => {
    render(<StateBoundary state={{ kind: 'loading', label: 'Today data' }} />)

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('Loading Today data…')).toBeInTheDocument()
  })

  it('explains an empty result instead of rendering zero-value facts', () => {
    render(
      <StateBoundary
        state={{
          kind: 'empty',
          title: 'No watchlist symbols',
          message: 'Add a symbol to begin daily research.',
        }}
      />,
    )

    expect(screen.getByRole('status', { name: 'No watchlist symbols' })).toHaveTextContent(
      'Add a symbol to begin daily research.',
    )
  })

  it('marks stale data with its exact last-updated timestamp', () => {
    render(
      <StateBoundary
        state={{
          kind: 'stale',
          title: 'Market context is stale',
          message: 'Decisions remain visible but should not be treated as current.',
          lastUpdatedAt: '2026-08-21T20:00:00Z',
        }}
      />,
    )

    expect(screen.getByRole('status', { name: 'Market context is stale' })).toHaveAttribute(
      'data-state',
      'stale',
    )
    expect(screen.getByText('2026-08-21T20:00:00Z')).toHaveAttribute(
      'datetime',
      '2026-08-21T20:00:00Z',
    )
  })

  it('names every degraded provider while retaining partial content', () => {
    render(
      <StateBoundary
        state={{
          kind: 'degraded',
          title: 'Provider coverage degraded',
          message: 'Available evidence is shown with reduced coverage.',
          providers: ['SEC', 'Options'],
        }}
      >
        <p>Partial market context</p>
      </StateBoundary>,
    )

    const status = screen.getByRole('status', { name: 'Provider coverage degraded' })
    expect(status).toHaveTextContent('SEC')
    expect(status).toHaveTextContent('Options')
    expect(screen.getByText('Partial market context')).toBeInTheDocument()
  })

  it('uses an alert for failure and offers a deterministic recovery path', () => {
    render(
      <StateBoundary
        state={{
          kind: 'failure',
          title: 'Today data unavailable',
          message: 'The request failed before a trustworthy snapshot was available.',
          retryHref: '/',
        }}
      />,
    )

    expect(screen.getByRole('alert')).toHaveAccessibleName('Today data unavailable')
    expect(screen.getByRole('link', { name: 'Try again' })).toHaveAttribute('href', '/')
  })

  it('renders successful content without an artificial status wrapper', () => {
    render(
      <StateBoundary state={{ kind: 'success' }}>
        <h2>Market regime</h2>
      </StateBoundary>,
    )

    expect(screen.getByRole('heading', { name: 'Market regime' })).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
