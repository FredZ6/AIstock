'use client'

import Link from 'next/link'
import { type ReactNode, useEffect, useState } from 'react'

import { MarketThemeContext } from '../market/tradingview-widget'

const navigation = [
  { href: '/', label: 'Today' },
  { href: '/watchlist', label: 'Watchlist' },
  { href: '/research', label: 'Research' },
  { href: '/runs/latest', label: 'Run Trace' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/alerts', label: 'Alerts' },
  { href: '/weekly-review', label: 'Weekly Review' },
  { href: '/eval', label: 'Eval & Admin' },
] as const

type AppShellProps = {
  children: ReactNode
  currentPath: string
}

export function AppShell({ children, currentPath }: AppShellProps) {
  const researchPath = currentPath.startsWith('/research/') ? currentPath : '/research'
  const contextualNavigation = navigation.map((item) => item.label === 'Research'
    ? { ...item, href: researchPath }
    : item)
  const currentLabel = currentPath.startsWith('/research/')
    ? 'Research'
    : navigation.find((item) => item.href === currentPath)?.label ?? 'Research'
  const [dark, setDark] = useState<boolean | null>(null)
  const [navigationOpen, setNavigationOpen] = useState(false)

  useEffect(() => {
    const storedDark = window.localStorage?.getItem?.('theme') === 'dark'
    setDark(storedDark)
    document.documentElement.dataset.theme = storedDark ? 'dark' : 'light'
  }, [])

  useEffect(() => {
    function dismissNavigation(event: KeyboardEvent) {
      if (event.key === 'Escape') setNavigationOpen(false)
    }

    document.addEventListener('keydown', dismissNavigation)
    return () => document.removeEventListener('keydown', dismissNavigation)
  }, [])

  function toggleTheme() {
    const next = dark !== true
    setDark(next)
    document.documentElement.dataset.theme = next ? 'dark' : 'light'
    window.localStorage?.setItem?.('theme', next ? 'dark' : 'light')
  }

  return (
    <MarketThemeContext.Provider value={dark === null ? null : dark ? 'dark' : 'light'}>
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="app-chrome">
        <div className="brand-lockup">
          <span aria-hidden="true" className="brand-mark">A</span>
          <p><strong>AI Stock Research</strong><span>Evidence before action</span></p>
        </div>
        <span aria-hidden="true" className="mobile-current">Current · {currentLabel}</span>
        <div className="chrome-actions">
          <button
            aria-controls="primary-navigation"
            aria-expanded={navigationOpen}
            aria-label={`${navigationOpen ? 'Close' : 'Open'} navigation`}
            className="navigation-toggle"
            onClick={() => setNavigationOpen((open) => !open)}
            type="button"
          >
            <span aria-hidden="true" className="navigation-toggle-icon">
              <span />
              <span />
              <span />
            </span>
          </button>
          <nav
            aria-label="Primary"
            className="primary-nav"
            data-open={navigationOpen}
            id="primary-navigation"
          >
            {contextualNavigation.map((item) => (
              <Link
                aria-current={currentPath === item.href ? 'page' : undefined}
                className="nav-link"
                data-current={currentPath === item.href ? 'true' : undefined}
                href={item.href}
                key={item.href}
                onClick={() => setNavigationOpen(false)}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <button
            aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}
            aria-pressed={dark === true}
            className="theme-toggle"
            onClick={toggleTheme}
            type="button"
          >
            <span aria-hidden="true">{dark ? '☀︎' : '☾'}</span>
          </button>
        </div>
      </header>
      <main className={`app-main${currentPath === '/' ? ' app-main-today' : ''}`} id="main-content" tabIndex={-1}>{children}</main>
      <footer className="app-footer">
        <p>Paper Trading only · Not investment advice</p>
      </footer>
    </div>
    </MarketThemeContext.Provider>
  )
}
