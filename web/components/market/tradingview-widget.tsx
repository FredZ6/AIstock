'use client'

import { createContext, useContext, useEffect, useRef, useState } from 'react'

import {
  clearOwnedTradingViewHost,
  mountOwnedTradingViewScript,
  useTradingViewAdmission,
} from './tradingview-containment'
import type { TradingViewLoadState } from './tradingview-containment'

type Theme = 'dark' | 'light'
type WidgetKind = 'mini-chart' | 'symbol-overview'

const scripts: Record<WidgetKind, string> = {
  'mini-chart': 'https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js',
  'symbol-overview': 'https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js',
}

export const MarketThemeContext = createContext<Theme | null>(null)

function marketSymbol(symbol: string) {
  const normalized = symbol.trim().toUpperCase()
  return /^[A-Z][A-Z0-9.-]{0,9}$/.test(normalized) ? `NASDAQ:${normalized}` : null
}

function widgetConfig(kind: WidgetKind, symbol: string | undefined, theme: Theme) {
  const proName = symbol && marketSymbol(symbol)
  if (!proName) return null

  if (kind === 'symbol-overview') {
    return {
      autosize: true,
      chartOnly: false,
      chartType: 'area',
      colorTheme: theme,
      dateRanges: ['1d|1', '1m|1D', '3m|60', '12m|1D', '60m|1W', 'all|1M'],
      fontFamily: '-apple-system, BlinkMacSystemFont, Inter, sans-serif',
      hideDateRanges: false,
      hideMarketStatus: true,
      hideSymbolLogo: false,
      isTransparent: false,
      locale: 'en',
      noTimeScale: false,
      scaleMode: 'Normal',
      scalePosition: 'right',
      showMA: false,
      showVolume: false,
      symbols: [[`${proName}|1D`]],
      width: '100%',
    }
  }

  return {
    autosize: true,
    chartOnly: false,
    colorTheme: theme,
    dateRange: '1M',
    isTransparent: false,
    largeChartUrl: '',
    locale: 'en',
    noTimeScale: true,
    symbol: proName,
  }
}

export function TradingViewWidget({ kind, symbol }: { kind: WidgetKind; symbol?: string }) {
  const container = useRef<HTMLDivElement>(null)
  const theme = useContext(MarketThemeContext)
  const [loadState, setLoadState] = useState<TradingViewLoadState>('deferred')
  const normalizedSymbol = symbol?.trim().toUpperCase()
  const admitted = useTradingViewAdmission(
    container,
    Boolean(theme && widgetConfig(kind, normalizedSymbol, theme)),
  )
  const label = `${normalizedSymbol} current market ${kind === 'symbol-overview' ? 'overview' : 'chart'}`
  const externalUrl = normalizedSymbol
    ? `https://www.tradingview.com/symbols/${encodeURIComponent(normalizedSymbol)}/`
    : 'https://www.tradingview.com/markets/stocks-usa/'

  useEffect(() => {
    const target = container.current
    const config = theme && widgetConfig(kind, normalizedSymbol, theme)
    if (!target || !config || !admitted) return

    const timer = window.setTimeout(() => {
      const widget = document.createElement('div')
      widget.className = 'tradingview-widget-container__widget'
      mountOwnedTradingViewScript({
        target,
        owner: `${kind}:${normalizedSymbol}`,
        source: scripts[kind],
        config,
        content: [widget],
        onStateChange: setLoadState,
      })
    }, 0)

    return () => {
      window.clearTimeout(timer)
      clearOwnedTradingViewHost(target)
    }
  }, [admitted, kind, normalizedSymbol, theme])

  return (
    <section aria-label={label} className={`market-widget market-widget-${kind} market-widget-${loadState}`}>
      <div className="market-widget-heading">
        <span>Current market reference</span>
        <small>Not decision-time evidence</small>
      </div>
      <div
        aria-label={kind === 'symbol-overview' ? `Scrollable ${symbol} TradingView overview` : undefined}
        className="tradingview-widget-container"
        ref={container}
        role={kind === 'symbol-overview' ? 'region' : undefined}
        tabIndex={kind === 'symbol-overview' ? 0 : undefined}
      />
      <div
        aria-label={loadState === 'failed' ? 'Current market reference unavailable' : undefined}
        className="market-widget-fallback"
        role={loadState === 'failed' ? 'status' : undefined}
      >
        <span>
          {loadState === 'failed'
            ? 'TradingView could not be loaded.'
            : loadState === 'deferred'
              ? 'Current market chart loads when this section nears the viewport.'
              : loadState === 'loading'
                ? 'Loading current market reference…'
                : 'External current-market source'}
        </span>
        <a href={externalUrl} rel="noopener nofollow" target="_blank">
          Open {normalizedSymbol ?? 'US stock markets'} on TradingView
        </a>
      </div>
    </section>
  )
}
