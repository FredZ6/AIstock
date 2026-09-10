'use client'

import Link from 'next/link'
import { FormEvent, useState } from 'react'

import type { ApiWatchlistItem, WatchlistSnapshot } from '../../lib/product-types'
import type { EarningsEvent, LiveDataStatus, MarketBar, MarketQuote } from '../../lib/server/live-data-api'
import { formatMoney, formatPercent } from '../../lib/format'
import { parseAwareInstant } from '../../lib/time'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { TradingViewTickerList } from '../market/tradingview-ticker-list'
import { StateBoundary } from '../states/state-boundary'
import { FixtureNotice, PageHeading, QualityFacts, Signal } from '../ui/product-ui'
import { WatchlistApiControls } from './watchlist-api-controls'
import { companyName } from './watchlist-display'

export function ApiWatchlistPage({
  asOf,
  earningsBySymbol = {},
  historiesBySymbol = {},
  items,
  missingSymbols = [],
  quoteStatus = 'SUCCESS',
  quotes,
}: {
  asOf: string
  earningsBySymbol?: Record<string, EarningsEvent[]>
  historiesBySymbol?: Record<string, MarketBar[]>
  items: ApiWatchlistItem[]
  missingSymbols?: string[]
  quoteStatus?: LiveDataStatus
  quotes: MarketQuote[]
}) {
  const hasCompleteMarketQuotes = quoteStatus === 'SUCCESS' && items.length > 0 && missingSymbols.length === 0 && quotes.length === items.length
  const missingTrends = items.filter((item) => (historiesBySymbol[item.symbol]?.length ?? 0) < 2)
  const staleTrends = items.filter((item) => {
    const latest = historiesBySymbol[item.symbol]?.at(-1)
    return latest
      ? parseAwareInstant(asOf).getTime() - parseAwareInstant(latest.availableAt).getTime() > 24 * 60 * 60 * 1000
      : false
  })
  const missingEarnings = items.filter((item) => !(item.symbol in earningsBySymbol))
  const missing = [
    ...(quoteStatus === 'DEGRADED' ? ['Market quote quality'] : []),
    ...(hasCompleteMarketQuotes || quoteStatus === 'DEGRADED' ? [] : missingSymbols.length ? missingSymbols.map((symbol) => `${symbol} market quote`) : ['Market data']),
    ...missingTrends.map((item) => `${item.symbol} trend`),
    ...staleTrends.map((item) => `${item.symbol} trend stale`),
    'Research',
    ...missingEarnings.map((item) => `${item.symbol} earnings`),
    'Decision history',
  ]
  return (
    <AppShell currentPath="/watchlist">
      <PageHeading
        asOf={asOf}
        eyebrow="Discover · API Mode"
        title="Watchlist"
        summary="Persisted configuration and point-in-time market quotes from FastAPI; missing enrichment remains explicit."
      />
      <StateBoundary state={{
        kind: 'degraded',
        title: hasCompleteMarketQuotes ? 'Research enrichment unavailable' : 'Market and research data unavailable',
        message: hasCompleteMarketQuotes
          ? 'ALPACA market quotes remain visible. Missing research facts are never replaced with Fixture data.'
          : 'Persisted schedules and thresholds remain usable. Missing facts are never replaced with Fixture data.',
        providers: missing,
      }}>
        <WatchlistApiControls asOf={asOf} earningsBySymbol={earningsBySymbol} historiesBySymbol={historiesBySymbol} items={items} quotes={quotes} />
      </StateBoundary>
    </AppShell>
  )
}

export function WatchlistFailurePage({ asOf }: { asOf: string }) {
  return (
    <AppShell currentPath="/watchlist">
      <PageHeading asOf={asOf} eyebrow="Discover · API Mode" title="Watchlist" summary="Persisted Watchlist data could not be loaded." />
      <StateBoundary state={{
        kind: 'failure',
        title: 'Watchlist unavailable',
        message: 'FastAPI did not return a valid Watchlist response. Fixture data was not substituted.',
        retryHref: '/watchlist',
      }} />
    </AppShell>
  )
}

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
        <ol className="ranked-watchlist" aria-label="Ranked research watchlist">
          {symbols.map((item, index) => <li key={item.symbol}>
            <span className="watchlist-rank" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
            <div className="watchlist-identity"><Link href={`/research/${item.symbol}`}>{item.symbol}</Link><span>{companyName(item.symbol)}</span></div>
            <div className="watchlist-trend" aria-label={`${item.symbol} compact trend`} data-direction={item.dailyReturn.startsWith('-') ? 'negative' : 'positive'}><span aria-hidden="true">{item.dailyReturn.startsWith('-') ? '↘' : '↗'}</span> {formatPercent(item.dailyReturn)}</div>
            <div className="watchlist-quote"><strong>{formatMoney(item.price, 'USD')}</strong><Signal tone={item.researchOpinion}>{item.researchOpinion}</Signal></div>
            <div className="watchlist-provenance"><QualityFacts quality={item.dataQuality} /><time dateTime={item.lastResearchAt}>Persisted {formatDualTime(item.lastResearchAt).newYork}</time></div>
          </li>)}
        </ol>
        <section className="watchlist-configuration" aria-labelledby="watchlist-controls-title">
        <div className="watchlist-controls">
          <div><h3 id="watchlist-controls-title">Watchlist controls</h3><p>Daily research, intraday monitoring, and thresholds are a session-only configuration draft in Fixture Mode.</p></div>
          <form onSubmit={addSymbol}>
            <label htmlFor="add-symbol">Add symbol</label>
            <input id="add-symbol" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={10} autoCapitalize="characters" />
            <button type="submit">Add to watchlist</button>
          </form>
        </div>
        <div className="watchlist-config-list">{symbols.map((item) => <section aria-label={`${item.symbol} settings`} key={item.symbol}><details><summary>{item.symbol} settings · {item.portfolioAction}</summary><div className="watchlist-config-heading"><h4>{item.symbol}</h4><span><Signal tone={item.portfolioAction}>{item.portfolioAction}</Signal></span></div><div className="watchlist-settings">
                <label><input type="checkbox" checked={item.dailyResearch} onChange={(event) => updateSymbol(item.symbol, { dailyResearch: event.target.checked })} /> <span>{item.symbol} daily research</span></label>
                <label><input type="checkbox" checked={item.intradayMonitoring} onChange={(event) => updateSymbol(item.symbol, { intradayMonitoring: event.target.checked })} /> <span>{item.symbol} intraday monitoring</span></label>
                <label><span>{item.symbol} alert threshold</span><input aria-label={`${item.symbol} alert threshold`} inputMode="decimal" value={item.alertThreshold} onChange={(event) => updateSymbol(item.symbol, { alertThreshold: event.target.value })} /></label>
              </div><p className="watchlist-setting-note">Next earnings: {item.nextEarningsAt ? <time dateTime={item.nextEarningsAt}>{new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(parseAwareInstant(item.nextEarningsAt))}</time> : 'Not in fixture'}</p></details></section>)}</div>
        </section>
        <TradingViewTickerList symbols={symbols.map((item) => item.symbol)} />
      </section>
    </AppShell>
  )
}
