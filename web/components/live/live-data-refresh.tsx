'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

const REFRESH_INTERVAL_MS = 60_000

export function LiveDataRefresh() {
  const router = useRouter()

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible' && navigator.onLine) router.refresh()
    }, REFRESH_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [router])

  return (
    <span aria-label="Live data refresh" className="sr-only">
      Persisted data refreshes every 60 seconds while this page is visible.
    </span>
  )
}
