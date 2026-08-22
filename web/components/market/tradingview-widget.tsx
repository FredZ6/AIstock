'use client'

import { createContext, useContext, useEffect, useRef } from 'react'

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
  const label = `${symbol} current market ${kind === 'symbol-overview' ? 'overview' : 'chart'}`

  useEffect(() => {
    const target = container.current
    const config = theme && widgetConfig(kind, symbol, theme)
    if (!target || !config) return

    const timer = window.setTimeout(() => {
      target.replaceChildren()
      const widget = document.createElement('div')
      widget.className = 'tradingview-widget-container__widget'
      const attribution = document.createElement('div')
      attribution.className = 'tradingview-widget-copyright'
      const link = document.createElement('a')
      link.href = symbol
        ? `https://www.tradingview.com/symbols/${encodeURIComponent(symbol.toUpperCase())}/`
        : 'https://www.tradingview.com/markets/stocks-usa/'
      link.rel = 'noopener nofollow'
      link.target = '_blank'
      link.textContent = symbol ? `${symbol.toUpperCase()} market data` : 'US technology markets'
      attribution.append(link, ' by TradingView')

      const script = document.createElement('script')
      script.async = true
      script.src = scripts[kind]
      script.type = 'text/javascript'
      script.textContent = JSON.stringify(config)
      target.append(widget, attribution, script)
    }, 0)

    return () => {
      window.clearTimeout(timer)
      target.replaceChildren()
    }
  }, [kind, symbol, theme])

  return (
    <section aria-label={label} className={`market-widget market-widget-${kind}`}>
      <div className="market-widget-heading">
        <span>Current market reference</span>
        <small>Not decision-time evidence</small>
      </div>
      <div className="tradingview-widget-container" ref={container} />
    </section>
  )
}
