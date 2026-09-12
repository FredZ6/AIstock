import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { StateBoundary } from '../components/states/state-boundary'

const refresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh }),
}))

describe('StateBoundary', () => {
  beforeEach(() => refresh.mockReset())
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
          actionHref: '/watchlist',
          actionLabel: 'Configure watchlist',
        }}
      />,
    )

    expect(screen.getByRole('status', { name: 'No watchlist symbols' })).toHaveTextContent(
      'Add a symbol to begin daily research.',
    )
    expect(screen.getByRole('link', { name: 'Configure watchlist' })).toHaveAttribute('href', '/watchlist')
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

  it('rejects a naive stale timestamp', () => {
    expect(() =>
      render(
        <StateBoundary
          state={{
            kind: 'stale',
            title: 'Market context is stale',
            message: 'Decisions remain visible but should not be treated as current.',
            lastUpdatedAt: '2026-08-21T20:00:00',
          }}
        />,
      ),
    ).toThrow(/timezone/i)
  })

  it('names every degraded provider while retaining partial content', () => {
    render(
      <StateBoundary
        state={{
          kind: 'degraded',
          title: 'Provider coverage degraded',
          message: 'Available evidence is shown with reduced coverage.',
          providers: ['SEC', 'Options'],
          actionHref: '/watchlist',
          actionLabel: 'Review provider coverage',
        }}
      >
        <p>Partial market context</p>
      </StateBoundary>,
    )

    const status = screen.getByRole('status', { name: 'Provider coverage degraded' })
    expect(status).toHaveClass('surface-card')
    expect(status).toHaveTextContent('SEC')
    expect(status).toHaveTextContent('Options')
    const disclosure = screen.getByText('2 unavailable facts').closest('details')
    expect(disclosure).not.toHaveAttribute('open')
    expect(screen.getByText('Partial market context')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review provider coverage' })).toHaveAttribute('href', '/watchlist')
  })

  it('keeps available records visible when a response is partial', () => {
    render(
      <StateBoundary
        state={{
          kind: 'partial',
          title: 'Partial result',
          message: 'Two symbols are still pending.',
          missing: ['AMD', 'TSLA'],
        }}
      >
        <p>Three verified symbols</p>
      </StateBoundary>,
    )

    expect(screen.getByRole('status', { name: 'Partial result' })).toBeInTheDocument()
    expect(screen.getByText('AMD')).toBeInTheDocument()
    expect(screen.getByText('Three verified symbols')).toBeInTheDocument()
  })

  it('uses an alert for failure and offers a deterministic recovery path', () => {
    render(
      <StateBoundary
        state={{
          kind: 'failure',
          title: 'Today data unavailable',
          message: 'The request failed before a trustworthy snapshot was available.',
          retry: true,
        }}
      />,
    )

    expect(screen.getByRole('alert')).toHaveAccessibleName('Today data unavailable')
    expect(screen.getByRole('alert')).toHaveClass('surface-card')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(refresh).toHaveBeenCalledOnce()
    expect(screen.queryByRole('link', { name: 'Try again' })).not.toBeInTheDocument()
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
