'use client'

import { useEffect } from 'react'

import { AppShell } from '../components/layout/app-shell'

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('app-router-error-boundary', { digest: error.digest })
  }, [error])

  return (
    <AppShell currentPath="/">
      <section aria-label="Unexpected page failure" className="state-surface surface-card" data-state="failure" role="alert">
        <p className="state-label">Failure</p>
        <h1>Page unavailable</h1>
        <p className="state-message">The page could not be rendered safely. No Fixture data was substituted.</p>
        <button className="state-retry" onClick={reset} type="button">Try again</button>
      </section>
    </AppShell>
  )
}
