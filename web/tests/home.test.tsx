import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Home from '../app/page'

describe('home page', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('uses Today as the fixture-mode landing page without presenting fixtures as market data', async () => {
    vi.stubEnv('WEB_DATA_MODE', 'fixture')
    render(await Home())
    expect(screen.getByRole('heading', { name: 'Today' })).toBeInTheDocument()
    expect(screen.getByText('Fixture Mode')).toBeInTheDocument()
    expect(screen.getByText(/Frozen synthetic fixture · not current market data/i)).toBeInTheDocument()
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
  })
})
