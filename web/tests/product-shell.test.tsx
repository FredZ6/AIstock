import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { AppShell } from '../components/layout/app-shell'

const storedThemes = new Map<string, string>()

describe('product shell', () => {
  beforeEach(() => {
    storedThemes.clear()
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => storedThemes.get(key) ?? null,
        removeItem: (key: string) => storedThemes.delete(key),
        setItem: (key: string, value: string) => storedThemes.set(key, value),
      },
    })
  })

  afterEach(() => {
    delete document.documentElement.dataset.theme
    window.localStorage.removeItem('theme')
  })

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
      { href: '/research', label: 'Research' },
      { href: '/runs/latest', label: 'Run Trace' },
      { href: '/portfolio', label: 'Portfolio' },
      { href: '/alerts', label: 'Alerts' },
      { href: '/weekly-review', label: 'Weekly Review' },
      { href: '/eval', label: 'Eval & Admin' },
    ])
    expect(screen.getByRole('link', { name: 'Today' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('region', { name: 'Current market ticker' })).not.toBeInTheDocument()
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
  })

  it('preserves the current research symbol in contextual navigation', () => {
    render(
      <AppShell currentPath="/research/MSFT">
        <h1>MSFT research</h1>
      </AppShell>,
    )

    expect(screen.getByRole('link', { name: 'Research' })).toHaveAttribute('href', '/research/MSFT')
    expect(screen.getByRole('link', { name: 'Research' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Current · Research')).toBeInTheDocument()
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
    expect(screen.getByText('Current · Portfolio')).toHaveAttribute('aria-hidden', 'true')
  })

  it('switches to a persistent dark theme and exposes the inverse action', () => {
    render(
      <AppShell currentPath="/">
        <h1>Today</h1>
      </AppShell>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(window.localStorage.getItem('theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('opens and dismisses an explicit compact navigation menu', () => {
    render(
      <AppShell currentPath="/portfolio">
        <h1>Portfolio</h1>
      </AppShell>,
    )

    const openNavigation = screen.getByRole('button', { name: 'Open navigation' })
    expect(openNavigation).toHaveAttribute('aria-expanded', 'false')
    expect(openNavigation).toHaveAttribute('aria-controls', 'primary-navigation')
    expect(screen.getByRole('navigation', { name: 'Primary' })).toHaveAttribute(
      'data-open',
      'false',
    )

    fireEvent.click(openNavigation)

    const closeNavigation = screen.getByRole('button', { name: 'Close navigation' })
    expect(closeNavigation).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('navigation', { name: 'Primary' })).toHaveAttribute(
      'data-open',
      'true',
    )
    expect(screen.getByRole('link', { name: 'Weekly Review' })).toBeVisible()

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.getByRole('navigation', { name: 'Primary' })).toHaveAttribute(
      'data-open',
      'false',
    )
  })
})
