'use client'

import Link from 'next/link'
import { FormEvent, useState } from 'react'

import type { WatchlistSnapshot } from '../../lib/product-types'
import { formatMoney, formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { TradingViewWidget } from '../market/tradingview-widget'
import { FixtureNotice, PageHeading, QualityFacts, Signal } from '../ui/product-ui'

export function WatchlistPage({ snapshot }: { snapshot: WatchlistSnapshot }) {
  const [symbols, setSymbols] = useState(snapshot.symbols)
  const [draft, setDraft] = useState('')

  function addSymbol(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const symbol = draft.trim().toUpperCase()
    if (!/^[A-Z.]{1,10}$/.test(symbol) || symbols.some((item) => item.symbol === symbol) || symbols.length >= snapshot.limit) return
    setSymbols((items) => [...items, {
      symbol,
      price: '0',
      dailyReturn: '0',
      researchOpinion: 'ABSTAIN',
      portfolioAction: 'NO_ACTION',
      lastResearchAt: snapshot.asOf,
      dailyResearch: false,
      intradayMonitoring: false,
      alertThreshold: '0.025',
      nextEarningsAt: null,
      dataQuality: { conflict: false, coverage: '0', delaySeconds: '0', freshness: 'STALE', provider: 'fixture-session-draft' },
    }])
    setDraft('')
  }

  function updateSymbol(symbol: string, patch: Partial<(typeof symbols)[number]>) {
    setSymbols((items) => items.map((item) => item.symbol === symbol ? { ...item, ...patch } : item))
  }

  return (
    <AppShell currentPath="/watchlist">
      <PageHeading asOf={snapshot.asOf} eyebrow="Discover" title="Watchlist" summary="Rank attention without turning uncertainty into a trading instruction." />
      <FixtureNotice />
      <section className="terminal-section first-section" aria-labelledby="watchlist-count">
        <div className="section-heading"><div><p className="section-kicker">Research universe</p><h2 id="watchlist-count">{symbols.length} of {snapshot.limit} symbols</h2></div><span className="muted-copy">Long-only US technology equities</span></div>
        <section className="watchlist-controls" aria-labelledby="watchlist-controls-title">
          <div><h3 id="watchlist-controls-title">Watchlist controls</h3><p>Daily research, intraday monitoring, and thresholds are a session-only configuration draft in Fixture Mode.</p></div>
          <form onSubmit={addSymbol}>
            <label htmlFor="add-symbol">Add symbol</label>
            <input id="add-symbol" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={10} autoCapitalize="characters" />
            <button type="submit">Add to watchlist</button>
          </form>
        </section>
        <div className="table-scroll">
          <table aria-label="Research watchlist">
            <thead><tr><th scope="col">Symbol</th><th scope="col">Price</th><th scope="col">Day</th><th scope="col">Research opinion</th><th scope="col">Portfolio action</th><th scope="col">Next earnings</th><th scope="col">Monitoring</th><th scope="col">Last research</th><th scope="col">Data quality</th></tr></thead>
            <tbody>{symbols.map((item) => <tr key={item.symbol}>
              <th scope="row"><Link href={`/research/${item.symbol}`}>{item.symbol}</Link></th>
              <td>{formatMoney(item.price, 'USD')}</td><td>{formatPercent(item.dailyReturn)}</td>
              <td><Signal tone={item.researchOpinion}>{item.researchOpinion}</Signal></td>
              <td><Signal tone={item.portfolioAction}>{item.portfolioAction}</Signal></td>
              <td>{item.nextEarningsAt ? <time dateTime={item.nextEarningsAt}>{new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(new Date(item.nextEarningsAt))}</time> : 'Not in fixture'}</td>
              <td><div className="watchlist-settings">
                <label><input type="checkbox" checked={item.dailyResearch} onChange={(event) => updateSymbol(item.symbol, { dailyResearch: event.target.checked })} /> <span>{item.symbol} daily research</span></label>
                <label><input type="checkbox" checked={item.intradayMonitoring} onChange={(event) => updateSymbol(item.symbol, { intradayMonitoring: event.target.checked })} /> <span>{item.symbol} intraday monitoring</span></label>
                <label><span>{item.symbol} alert threshold</span><input aria-label={`${item.symbol} alert threshold`} inputMode="decimal" value={item.alertThreshold} onChange={(event) => updateSymbol(item.symbol, { alertThreshold: event.target.value })} /></label>
              </div></td>
              <td><time dateTime={item.lastResearchAt}>{formatDualTime(item.lastResearchAt).newYork}</time></td>
              <td><QualityFacts quality={item.dataQuality} /></td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="mini-chart-grid">
          {symbols.map((item) => <TradingViewWidget key={item.symbol} kind="mini-chart" symbol={item.symbol} />)}
        </div>
      </section>
    </AppShell>
  )
}
