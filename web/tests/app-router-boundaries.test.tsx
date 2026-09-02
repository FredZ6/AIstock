import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import ErrorBoundary from '../app/error'
import Loading from '../app/loading'
import NotFound from '../app/not-found'

describe('App Router state boundaries', () => {
  it('announces native route loading without synthetic facts', () => {
    render(<Loading />)

    expect(screen.getByRole('status', { name: /Loading persisted data/ })).toBeInTheDocument()
    expect(screen.queryByText(/fixture mode/i)).not.toBeInTheDocument()
  })

  it('offers an accessible native retry for unexpected render failures', () => {
    const reset = vi.fn()
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    render(<ErrorBoundary error={new Error('private detail')} reset={reset} />)

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(reset).toHaveBeenCalledOnce()
    expect(screen.queryByText('private detail')).not.toBeInTheDocument()
    errorSpy.mockRestore()
  })

  it('provides a native not-found recovery route', () => {
    render(<NotFound />)

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Return to Today' })).toHaveAttribute('href', '/')
  })
})
