import Link from 'next/link'

import { AppShell } from '../components/layout/app-shell'

export default function NotFound() {
  return (
    <AppShell currentPath="/">
      <section aria-label="Page not found" className="state-surface surface-card" data-state="empty" role="status">
        <p className="state-label">Empty</p>
        <h1>Page not found</h1>
        <p className="state-message">This route does not exist or is no longer available.</p>
        <Link className="state-retry" href="/">Return to Today</Link>
      </section>
    </AppShell>
  )
}
