import Link from 'next/link'
import type { ReactNode } from 'react'

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
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="app-chrome">
        <div className="brand-lockup">
          <span aria-hidden="true" className="brand-mark">A</span>
          <p><strong>AI Stock Research</strong><span>Evidence before action</span></p>
        </div>
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
      </header>
      <main className="app-main" id="main-content">{children}</main>
      <footer className="app-footer">
        <p>Paper Trading only · Not investment advice</p>
      </footer>
    </div>
  )
}
