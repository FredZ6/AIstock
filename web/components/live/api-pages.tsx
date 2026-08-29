import Link from 'next/link'

import { formatMoney, formatPercent } from '../../lib/format'
import type {
  MarketQuote,
  PortfolioSummary,
  ProviderHealth,
  ResearchRecord,
} from '../../lib/server/live-data-api'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { TradingViewWidget } from '../market/tradingview-widget'
import { StateBoundary } from '../states/state-boundary'
import { PageHeading, Signal } from '../ui/product-ui'

export function ApiTodayPage({
  asOf,
  health,
  portfolio,
  quotes,
}: {
  asOf: string
  health: ProviderHealth
  portfolio: PortfolioSummary
  quotes: MarketQuote[]
}) {
  const unavailable = Object.entries(health.providers)
    .filter(([, provider]) => !provider.configured || provider.status === 'FAILURE' || provider.status === 'UNAVAILABLE')
    .map(([name]) => name.toUpperCase())
  const missing = [...unavailable, 'Market regime', 'Research decisions', 'Alerts']
  if (!portfolio.latestNav) missing.push('Portfolio NAV')
  return (
    <AppShell currentPath="/">
      <PageHeading asOf={asOf} eyebrow="Decision workspace · API Mode" title="Today" summary="Current persisted facts, with unavailable domains left explicit." />
      <StateBoundary compact state={{
        kind: 'degraded',
        title: 'Some decision facts are unavailable',
        message: 'Available backend facts remain visible. No Fixture data was substituted.',
        providers: missing,
      }}>
        <section className="terminal-section first-section" aria-labelledby="live-market-title">
          <div className="section-heading">
            <div><p className="section-kicker">Read-only market data</p><h2 id="live-market-title">Latest persisted quotes</h2></div>
            <span className="muted-copy">PIT cutoff · {formatDualTime(asOf).newYork}</span>
          </div>
          <ul className="watchlist-heatmap" aria-label="Latest persisted quotes">
            {quotes.map((quote) => <li key={quote.symbol}>
              <div className="heatmap-primary"><Link href={`/research/${quote.symbol}`}>{quote.symbol}</Link><strong>{formatMoney(quote.close, 'USD')}</strong></div>
              <span>{quote.provider} · {quote.coverage}</span>
              <small>Available {formatDualTime(quote.availableAt).newYork}</small>
            </li>)}
          </ul>
        </section>
        <section className="terminal-section" aria-labelledby="paper-portfolio-title">
          <p className="section-kicker">Paper only</p><h2 id="paper-portfolio-title">Paper portfolio</h2>
          {portfolio.latestNav
            ? <p><strong>{formatMoney(portfolio.latestNav.nav, 'USD')}</strong> at <time dateTime={portfolio.latestNav.eventTime}>{formatDualTime(portfolio.latestNav.eventTime).newYork}</time></p>
            : <p className="unavailable-value">No persisted NAV is available.</p>}
        </section>
      </StateBoundary>
    </AppShell>
  )
}

export function ApiResearchPage({
  asOf,
  quote,
  records,
  symbol,
}: {
  asOf: string
  quote: MarketQuote | null
  records: ResearchRecord[]
  symbol: string
}) {
  return (
    <AppShell currentPath={`/research/${symbol}`}>
      <PageHeading asOf={asOf} eyebrow="Research · API Mode" title={`${symbol} research`} summary="Persisted research only; current market reference remains separate from historical decision evidence." />
      <StateBoundary state={records.length ? { kind: 'success' } : {
        kind: 'degraded',
        title: 'Research evidence unavailable',
        message: 'No persisted research record exists for this symbol. No Fixture data was substituted.',
        providers: ['Research', 'Fundamentals', 'Earnings', 'News', 'Options', 'Analyst targets'],
      }}>
        {quote ? <section className="decision-hero" aria-label="Latest persisted market quote">
          <div><p className="section-kicker">Current market reference</p><h2>{quote.symbol}</h2><p className="thesis-copy">{formatMoney(quote.close, 'USD')}</p></div>
          <dl className="decision-facts"><div><dt>Provider</dt><dd>{quote.provider}</dd></div><div><dt>Coverage</dt><dd>{quote.coverage}</dd></div><div><dt>Available</dt><dd>{formatDualTime(quote.availableAt).newYork}</dd></div></dl>
        </section> : <p className="unavailable-value">Current quote unavailable.</p>}
        <TradingViewWidget kind="symbol-overview" symbol={symbol} />
        {records.map((record) => <article className="terminal-section" key={record.id}>
          <p className="section-kicker">Persisted thesis</p><h2>{record.direction}</h2><p>{record.summary}</p>
          <dl className="decision-facts"><div><dt>Opinion</dt><dd>{record.opinion ? <Signal tone={record.opinion}>{record.opinion}</Signal> : 'Unavailable'}</dd></div><div><dt>Confidence</dt><dd>{formatPercent(record.confidence, { signed: false })}</dd></div><div><dt>Horizon</dt><dd>{record.horizon}</dd></div></dl>
        </article>)}
      </StateBoundary>
    </AppShell>
  )
}

export function ApiPortfolioPage({ asOf, portfolio }: { asOf: string; portfolio: PortfolioSummary }) {
  return (
    <AppShell currentPath="/portfolio">
      <PageHeading asOf={asOf} eyebrow="Simulate · API Mode" title="AI Portfolio" summary="Persisted paper-trading facts only. No live brokerage path exists." />
      <StateBoundary state={portfolio.latestNav ? {
        kind: 'degraded',
        title: 'Portfolio evidence is partial',
        message: 'NAV is available, while positions, risk decisions, fills, and CashLedger enrichment are incomplete.',
        providers: ['Positions', 'Risk decisions', 'CashLedger'],
      } : {
        kind: 'failure',
        title: 'Portfolio facts unavailable',
        message: 'No persisted paper NAV exists. No Fixture portfolio was substituted.',
        retryHref: '/portfolio',
      }}>
        {portfolio.latestNav ? <section className="terminal-section first-section" aria-label="Latest paper NAV">
          <p className="section-kicker">Paper portfolio NAV</p><h2>{formatMoney(portfolio.latestNav.nav, 'USD')}</h2>
          <p><time dateTime={portfolio.latestNav.eventTime}>{formatDualTime(portfolio.latestNav.eventTime).newYork}</time></p>
        </section> : null}
      </StateBoundary>
    </AppShell>
  )
}

export function ApiFailurePage({ currentPath, title }: { currentPath: string; title: string }) {
  const asOf = new Date().toISOString()
  return (
    <AppShell currentPath={currentPath}>
      <PageHeading asOf={asOf} eyebrow="API Mode" title={title} summary="The backend response could not be safely rendered." />
      <StateBoundary state={{ kind: 'failure', title: `${title} unavailable`, message: 'The API was unavailable or returned an invalid contract. No Fixture data was substituted.', retryHref: currentPath }} />
    </AppShell>
  )
}
