'use client'

import { RefObject, useEffect, useState } from 'react'

export type TradingViewLoadState = 'deferred' | 'loading' | 'ready' | 'failed'

export function useTradingViewAdmission(target: RefObject<HTMLElement | null>, enabled: boolean) {
  const [admitted, setAdmitted] = useState(false)

  useEffect(() => {
    const element = target.current
    if (!enabled || !element) return

    if (typeof window.IntersectionObserver !== 'function') {
      setAdmitted(true)
      return
    }

    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return
      setAdmitted(true)
      observer.disconnect()
    }, { rootMargin: '320px 0px' })
    observer.observe(element)
    return () => observer.disconnect()
  }, [enabled, target])

  return admitted
}

export function configureOwnedTradingViewScript(
  script: HTMLScriptElement,
  owner: string,
  onStateChange: (state: TradingViewLoadState) => void,
) {
  script.dataset.tradingviewOwned = owner
  script.onload = () => onStateChange('ready')
  script.onerror = () => onStateChange('failed')
}
