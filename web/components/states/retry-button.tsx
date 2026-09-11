'use client'

import { useRouter } from 'next/navigation'

export function RetryButton() {
  const router = useRouter()

  return <button className="state-retry" onClick={() => router.refresh()} type="button">Try again</button>
}
