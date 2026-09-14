'use client'

import { useContext, useEffect, useRef, useState } from 'react'

import { MarketThemeContext } from './tradingview-widget'
import {
  clearOwnedTradingViewHost,
  mountOwnedTradingViewScript,
  useTradingViewAdmission,
} from './tradingview-containment'
import type { TradingViewLoadState } from './tradingview-containment'

const scriptUrl = 'https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js'
const symbolPattern = /^[A-Z][A-Z0-9.-]{0,9}$/
const exchangeBySymbol: Record<string, 'NASDAQ' | 'NYSE'> = {
  BE: 'NYSE',
  TSM: 'NYSE',
}

function tradingViewSymbols(symbols: string[]) {
  return [...new Set(symbols
    .map((symbol) => symbol.trim().toUpperCase())
    .filter((symbol) => symbolPattern.test(symbol)))]
    .map((symbol) => ({
      displayName: symbol,
      name: `${exchangeBySymbol[symbol] ?? 'NASDAQ'}:${symbol}`,
    }))
}

export function TradingViewTickerList({ symbols }: { symbols: string[] }) {
  const container = useRef<HTMLDivElement>(null)
  const theme = useContext(MarketThemeContext)
  const normalized = tradingViewSymbols(symbols)
  const normalizedKey = JSON.stringify(normalized)
  const [loadState, setLoadState] = useState<TradingViewLoadState>('deferred')
  const admitted = useTradingViewAdmission(container, Boolean(theme && normalized.length))

  useEffect(() => {
    const target = container.current
    if (!target || normalized.length === 0 || !theme || !admitted) return
    const configSymbols = JSON.parse(normalizedKey) as Array<{ displayName: string; name: string }>

    const timer = window.setTimeout(() => {
      const widget = document.createElement('div')
      widget.className = 'tradingview-widget-container__widget'
      widget.setAttribute('aria-label', 'TradingView current market tickers')
      const placeholder = document.createElement('p')
      placeholder.className = 'market-widget-placeholder'
      placeholder.textContent = 'Loading current market reference…'
      widget.append(placeholder)

      mountOwnedTradingViewScript({
        target,
        owner: 'market-quotes',
        source: scriptUrl,
        config: {
          colorTheme: theme,
          height: '100%',
          locale: 'en',
          showSymbolLogo: true,
          symbolsGroups: [{ name: 'Technology watchlist', symbols: configSymbols }],
          title: 'Technology watchlist',
          width: '100%',
        },
        content: [widget],
        onStateChange: setLoadState,
      })
    }, 0)

    return () => {
      window.clearTimeout(timer)
      clearOwnedTradingViewHost(target)
    }
  }, [admitted, normalized.length, normalizedKey, theme])

  return (
    <section aria-label="Current market reference" className="market-reference-list" data-evidence-scope="external-current-market">
      <div className="market-widget-heading">
        <span>Current market reference</span>
        <small>TradingView · Not decision-time evidence</small>
      </div>
      <div
        className={`market-reference-widget market-widget-${loadState}`}
        style={{ height: `${Math.min(40, Math.max(25, normalized.length * 2.25 + 6))}rem` }}
      >
        <div className="tradingview-widget-container" ref={container}>
          <p className="market-widget-placeholder">
            {normalized.length
              ? 'Loading current market reference is deferred until this section nears the viewport.'
              : 'Current market reference unavailable'}
          </p>
        </div>
        {normalized.length > 0 ? (
          <div
            aria-label={loadState === 'failed' ? 'Current market reference unavailable' : undefined}
            className="market-widget-fallback"
            role={loadState === 'failed' ? 'status' : undefined}
          >
            <span>{loadState === 'failed' ? 'TradingView could not be loaded.' : 'External current-market source'}</span>
            <a
              href="https://www.tradingview.com/markets/stocks-usa/"
              rel="noopener nofollow"
              target="_blank"
            >
              Open US stock markets on TradingView
            </a>
          </div>
        ) : null}
      </div>
    </section>
  )
}
