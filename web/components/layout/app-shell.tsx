'use client'

import Link from 'next/link'
import { type ReactNode, useEffect, useState } from 'react'

import { MarketThemeContext } from '../market/tradingview-widget'

const navigation = [
  { href: '/', label: 'Today' },
  { href: '/watchlist', label: 'Watchlist' },
  { href: '/research/NVDA', label: 'Research' },
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
  const currentLabel = navigation.find((item) => item.href === currentPath)?.label ?? 'Research'
  const [dark, setDark] = useState<boolean | null>(null)

  useEffect(() => {
    const storedDark = window.localStorage?.getItem?.('theme') === 'dark'
    setDark(storedDark)
    document.documentElement.dataset.theme = storedDark ? 'dark' : 'light'
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
          <nav aria-label="Primary" className="primary-nav">
            {navigation.map((item) => (
              <Link
                aria-current={currentPath === item.href ? 'page' : undefined}
                className="nav-link"
                data-current={currentPath === item.href ? 'true' : undefined}
                href={item.href}
                key={item.href}
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
      <main className={`app-main${currentPath === '/' ? ' app-main-today' : ''}`} id="main-content">{children}</main>
      <footer className="app-footer">
        <p>Paper Trading only · Not investment advice</p>
      </footer>
    </div>
    </MarketThemeContext.Provider>
  )
}
