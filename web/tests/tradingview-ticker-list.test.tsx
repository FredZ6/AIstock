import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TradingViewTickerList } from '../components/market/tradingview-ticker-list'
import { MarketThemeContext } from '../components/market/tradingview-widget'

function renderList(symbols: string[], theme: 'dark' | 'light' = 'light') {
  return render(
    <MarketThemeContext.Provider value={theme}>
      <TradingViewTickerList symbols={symbols} />
    </MarketThemeContext.Provider>,
  )
}

describe('TradingViewTickerList', () => {
  it('loads one vertical compact current-market widget with normalized symbols', async () => {
    renderList(['nvda', 'INVALID!', 'MSFT'])

    const region = screen.getByRole('region', { name: 'Current market reference' })
    expect(region).toHaveTextContent('Not decision-time evidence')
    expect(region).toHaveTextContent('Loading current market reference')

    await waitFor(() => expect(region.querySelector('script')).toHaveAttribute(
      'src',
      'https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js',
    ))
    const script = region.querySelector('script')
    const config = JSON.parse(script?.textContent ?? '{}')
    const sizingFrame = region.querySelector('.market-reference-widget')
    expect(sizingFrame).toHaveStyle({ height: '25rem' })
    expect(sizingFrame?.querySelector('.tradingview-widget-container')).toBeInTheDocument()
    expect(config.colorTheme).toBe('light')
    expect(config.symbolsGroups[0].symbols).toEqual([
      { displayName: 'NVDA', name: 'NASDAQ:NVDA' },
      { displayName: 'MSFT', name: 'NASDAQ:MSFT' },
    ])
  })

  it('keeps an explicit unavailable state when no symbols are valid', () => {
    renderList(['invalid!'])

    expect(screen.getByRole('region', { name: 'Current market reference' }))
      .toHaveTextContent('Current market reference unavailable')
  })

  it('uses the locked watchlist exchange for NYSE-listed symbols', async () => {
    renderList(['BE', 'TSM', 'NVDA'], 'dark')

    const region = screen.getByRole('region', { name: 'Current market reference' })
    await waitFor(() => expect(region.querySelector('script')).toBeInTheDocument())
    const config = JSON.parse(region.querySelector('script')?.textContent ?? '{}')
    expect(config.colorTheme).toBe('dark')
    expect(config.symbolsGroups[0].symbols.map(({ name }: { name: string }) => name))
      .toEqual(['NYSE:BE', 'NYSE:TSM', 'NASDAQ:NVDA'])
  })

  it('reserves a compact full-list height without a large empty tail', () => {
    renderList(['AVGO', 'BE', 'INTC', 'MRVL', 'MU', 'NBIS', 'NVDA', 'SKHY', 'SNDK', 'TSM', 'WDC'])

    expect(screen.getByRole('region', { name: 'Current market reference' })
      .querySelector('.market-reference-widget')).toHaveStyle({ height: '30.75rem' })
  })
})
