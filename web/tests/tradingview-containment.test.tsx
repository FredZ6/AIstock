import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { TradingViewTickerList } from '../components/market/tradingview-ticker-list'
import { MarketThemeContext, TradingViewWidget } from '../components/market/tradingview-widget'

type ObserverCallback = IntersectionObserverCallback

let observerCallback: ObserverCallback | undefined
const originalObserver = window.IntersectionObserver

function installIntersectionObserver() {
  observerCallback = undefined
  class TestIntersectionObserver {
    disconnect() {}
    observe() {}
    takeRecords(): IntersectionObserverEntry[] { return [] }
    unobserve() {}

    constructor(callback: ObserverCallback) {
      observerCallback = callback
    }
  }

  window.IntersectionObserver = TestIntersectionObserver as unknown as typeof IntersectionObserver
}

function reveal(element: Element) {
  const entry = { isIntersecting: true, target: element } as IntersectionObserverEntry
  act(() => observerCallback?.([entry], {} as IntersectionObserver))
}

afterEach(() => {
  window.IntersectionObserver = originalObserver
})

describe('TradingView containment', () => {
  it('waits until a symbol overview nears the viewport and injects one owned script', async () => {
    installIntersectionObserver()
    render(
      <MarketThemeContext.Provider value="light">
        <TradingViewWidget kind="symbol-overview" symbol="NVDA" />
      </MarketThemeContext.Provider>,
    )

    const region = screen.getByRole('region', { name: 'NVDA current market overview' })
    expect(region.querySelector('script')).not.toBeInTheDocument()
    expect(region).toHaveTextContent('loads when this section nears the viewport')

    reveal(region.querySelector('.tradingview-widget-container')!)
    reveal(region.querySelector('.tradingview-widget-container')!)

    await waitFor(() => expect(region.querySelectorAll('script[data-tradingview-owned]')).toHaveLength(1))
  })

  it('keeps an accessible current-market fallback when a symbol script fails', async () => {
    render(
      <MarketThemeContext.Provider value="dark">
        <TradingViewWidget kind="symbol-overview" symbol="NVDA" />
      </MarketThemeContext.Provider>,
    )

    const region = screen.getByRole('region', { name: 'NVDA current market overview' })
    await waitFor(() => expect(region.querySelector('script')).toBeInTheDocument())
    fireEvent.error(region.querySelector('script')!)

    expect(await screen.findByRole('status', { name: 'Current market reference unavailable' }))
      .toHaveTextContent('TradingView could not be loaded')
    expect(screen.getByRole('link', { name: 'Open NVDA on TradingView' }))
      .toHaveAttribute('href', 'https://www.tradingview.com/symbols/NVDA/')
    expect(region).toHaveTextContent('Not decision-time evidence')
  })

  it('lazy-loads the watchlist embed and preserves its external fallback on failure', async () => {
    installIntersectionObserver()
    render(
      <MarketThemeContext.Provider value="light">
        <TradingViewTickerList symbols={['NVDA', 'MSFT']} />
      </MarketThemeContext.Provider>,
    )

    const region = screen.getByRole('region', { name: 'Current market reference' })
    expect(region.querySelector('script')).not.toBeInTheDocument()
    reveal(region.querySelector('.tradingview-widget-container')!)

    await waitFor(() => expect(region.querySelectorAll('script[data-tradingview-owned]')).toHaveLength(1))
    fireEvent.error(region.querySelector('script')!)

    expect(await screen.findByRole('status', { name: 'Current market reference unavailable' }))
      .toHaveTextContent('TradingView could not be loaded')
    expect(screen.getByRole('link', { name: 'Open US stock markets on TradingView' }))
      .toHaveAttribute('href', 'https://www.tradingview.com/markets/stocks-usa/')
  })

  it('does not replace an owned watchlist script for an equivalent symbol array', async () => {
    const view = render(
      <MarketThemeContext.Provider value="light">
        <TradingViewTickerList symbols={['NVDA', 'MSFT']} />
      </MarketThemeContext.Provider>,
    )
    const region = screen.getByRole('region', { name: 'Current market reference' })
    await waitFor(() => expect(region.querySelector('script')).toBeInTheDocument())
    const originalScript = region.querySelector('script')

    view.rerender(
      <MarketThemeContext.Provider value="light">
        <TradingViewTickerList symbols={['NVDA', 'MSFT']} />
      </MarketThemeContext.Provider>,
    )

    await waitFor(() => expect(region.querySelector('script')).toBe(originalScript))
  })

  it('keeps the external fallback link after the provider script reports loaded', async () => {
    render(
      <MarketThemeContext.Provider value="light">
        <TradingViewWidget kind="mini-chart" symbol="NVDA" />
      </MarketThemeContext.Provider>,
    )
    const widget = screen.getByLabelText('NVDA current market chart')
    await waitFor(() => expect(widget.querySelector('script')).toBeInTheDocument())
    fireEvent.load(widget.querySelector('script')!)

    expect(screen.getByRole('link', { name: 'Open NVDA on TradingView' })).toBeInTheDocument()
  })
})
