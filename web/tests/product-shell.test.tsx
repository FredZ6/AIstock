import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AppShell } from '../components/layout/app-shell'

describe('product shell', () => {
  it('exposes the locked eight-page information architecture with Today as the landing page', () => {
    render(
      <AppShell currentPath="/">
        <h1>Today</h1>
      </AppShell>,
    )

    const navigation = screen.getByRole('navigation', { name: 'Primary' })
    const links = Array.from(navigation.querySelectorAll('a')).map((link) => ({
      href: link.getAttribute('href'),
      label: link.textContent,
    }))

    expect(links).toEqual([
      { href: '/', label: 'Today' },
      { href: '/watchlist', label: 'Watchlist' },
      { href: '/research/NVDA', label: 'Research' },
      { href: '/runs/latest', label: 'Run Trace' },
      { href: '/portfolio', label: 'Portfolio' },
      { href: '/alerts', label: 'Alerts' },
      { href: '/weekly-review', label: 'Weekly Review' },
      { href: '/eval', label: 'Eval & Admin' },
    ])
    expect(screen.getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
  })

  it('keeps the research-only safety boundary and keyboard entry point visible', () => {
    render(
      <AppShell currentPath="/portfolio">
        <h1>Portfolio</h1>
      </AppShell>,
    )

    expect(screen.getByText(/Paper Trading only/i)).toBeInTheDocument()
    expect(screen.getByText(/Not investment advice/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute(
      'href',
      '#main-content',
    )
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content')
  })
})
