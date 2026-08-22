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
    <div>
      <a href="#main-content">Skip to main content</a>
      <header>
        <p>AI Stock Research</p>
        <nav aria-label="Primary">
          {navigation.map((item) => (
            <Link
              aria-current={currentPath === item.href ? 'page' : undefined}
              href={item.href}
              key={item.href}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      <main id="main-content">{children}</main>
      <footer>
        <p>Paper Trading only · Not investment advice</p>
      </footer>
    </div>
  )
}
