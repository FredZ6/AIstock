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

export function mountOwnedTradingViewScript({
  target,
  owner,
  source,
  config,
  content,
  onStateChange,
}: {
  target: HTMLElement
  owner: string
  source: string
  config: object
  content: HTMLElement[]
  onStateChange: (state: TradingViewLoadState) => void,
}) {
  if (target.querySelector('script[data-tradingview-owned]')) return

  onStateChange('loading')
  const script = document.createElement('script')
  script.async = true
  script.src = source
  script.type = 'text/javascript'
  script.textContent = JSON.stringify(config)
  script.dataset.tradingviewOwned = owner
  script.onload = () => onStateChange('ready')
  script.onerror = () => onStateChange('failed')
  target.replaceChildren(...content, script)
}

export function clearOwnedTradingViewHost(target: HTMLElement) {
  const script = target.querySelector('script[data-tradingview-owned]') as HTMLScriptElement | null
  if (script) {
    script.onload = null
    script.onerror = null
  }
  target.replaceChildren()
}
