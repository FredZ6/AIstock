'use client'

import { useContext, useEffect, useMemo, useRef } from 'react'

import { MarketThemeContext } from './tradingview-widget'

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
  const normalized = useMemo(() => tradingViewSymbols(symbols), [symbols])

  useEffect(() => {
    const target = container.current
    if (!target || normalized.length === 0 || !theme) return

    const timer = window.setTimeout(() => {
      const widget = document.createElement('div')
      widget.className = 'tradingview-widget-container__widget'
      widget.setAttribute('aria-label', 'TradingView current market tickers')
      const placeholder = document.createElement('p')
      placeholder.className = 'market-widget-placeholder'
      placeholder.textContent = 'Loading current market reference…'
      widget.append(placeholder)

      const attribution = document.createElement('div')
      attribution.className = 'tradingview-widget-copyright'
      const link = document.createElement('a')
      link.href = 'https://www.tradingview.com/markets/stocks-usa/'
      link.rel = 'noopener nofollow'
      link.target = '_blank'
      link.textContent = 'Market data'
      attribution.append(link, ' by TradingView')

      const script = document.createElement('script')
      script.async = true
      script.src = scriptUrl
      script.type = 'text/javascript'
      script.textContent = JSON.stringify({
        colorTheme: theme,
        height: '100%',
        locale: 'en',
        showSymbolLogo: true,
        symbolsGroups: [{ name: 'Technology watchlist', symbols: normalized }],
        title: 'Technology watchlist',
        width: '100%',
      })
      target.replaceChildren(widget, attribution, script)
    }, 0)

    return () => {
      window.clearTimeout(timer)
      target.replaceChildren()
    }
  }, [normalized, theme])

  return (
    <section aria-label="Current market reference" className="market-reference-list">
      <div className="market-widget-heading">
        <span>Current market reference</span>
        <small>TradingView · Not decision-time evidence</small>
      </div>
      <div
        className="market-reference-widget"
        style={{ height: `${Math.min(40, Math.max(25, normalized.length * 2.25 + 6))}rem` }}
      >
        <div className="tradingview-widget-container" ref={container}>
          <p className="market-widget-placeholder">
            {normalized.length ? 'Loading current market reference…' : 'Current market reference unavailable'}
          </p>
        </div>
      </div>
    </section>
  )
}
