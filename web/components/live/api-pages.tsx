import Link from 'next/link'

import { initializePortfolioAction } from '../../app/portfolio/actions'
import { formatDecimal, formatMoney, formatPercent } from '../../lib/format'
import type {
  DataQuality,
  FinancialFact,
  MarketQuote,
  PortfolioSummary,
  ProviderHealth,
  ResearchRecord,
  SecFiling,
  WeeklyReviewDetail,
} from '../../lib/server/live-data-api'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { TradingViewWidget } from '../market/tradingview-widget'
import { TradingViewTickerList } from '../market/tradingview-ticker-list'
import { StateBoundary } from '../states/state-boundary'
import { PageHeading, Signal } from '../ui/product-ui'

export function ApiCollectionPage({
  asOf,
  count,
  currentPath,
  emptyTitle,
  title,
}: {
  asOf: string
  count: number
  currentPath: string
  emptyTitle: string
  title: string
}) {
  return (
    <AppShell currentPath={currentPath}>
      <PageHeading asOf={asOf} eyebrow="API Mode" title={title} summary="Persisted backend facts only. No Fixture data was substituted." />
      <StateBoundary state={count === 0 ? {
        kind: 'empty',
        title: emptyTitle,
        message: 'The authoritative backend returned no records at this point-in-time cutoff.',
      } : { kind: 'success' }}>
        <section className="terminal-section first-section" aria-label={`${title} persisted records`}>
          <p className="section-kicker">Persisted records</p><h2>{count}</h2>
          <p>Detailed presentation remains constrained to the locked API contract.</p>
        </section>
      </StateBoundary>
    </AppShell>
  )
}

export function ApiRunMetadataPage({ run }: { run: import('../../lib/server/live-data-api').ResearchRun }) {
  return (
    <AppShell currentPath={`/runs/${run.runId}`}>
      <PageHeading asOf={run.decisionTime} eyebrow="Audit · API Mode" title={`Research run · ${run.symbol ?? 'Portfolio'}`} summary="Persisted run admission and status facts. Durable events remain available through the SSE contract." />
      <section className="run-overview" aria-label="Persisted run metadata">
        <div><p className="section-kicker">Status</p><Signal tone={run.status}>{run.status}</Signal><small>{run.runId}</small></div>
        <dl className="budget-strip"><div><dt>Run type</dt><dd>{run.runType}</dd></div><div><dt>Decision time</dt><dd>{formatDualTime(run.decisionTime).newYork}</dd></div><div><dt>Data cutoff</dt><dd>{formatDualTime(run.dataCutoff).newYork}</dd></div></dl>
      </section>
    </AppShell>
  )
}

export function ApiTodayPage({
  asOf,
  health,
  portfolio,
  quotes,
  unavailableDomains = [],
}: {
  asOf: string
  health: ProviderHealth | null
  portfolio: PortfolioSummary | null
  quotes: MarketQuote[]
  unavailableDomains?: string[]
}) {
  const unavailableProviders = health ? Object.entries(health.providers)
    .filter(([, provider]) => !provider.configured || provider.status === 'FAILURE' || provider.status === 'UNAVAILABLE')
    .map(([name]) => name.toUpperCase()) : ['Provider health']
  const unique = (items: string[]) => [...new Set(items)]
  const providerDomains = unavailableDomains.filter((domain) => /provider/i.test(domain))
  const marketDomains = unavailableDomains.filter((domain) => /market|quote/i.test(domain))
  const decisionDomains = unavailableDomains.filter(
    (domain) => !providerDomains.includes(domain) && !marketDomains.includes(domain),
  )
  const decisionFacts = [...decisionDomains, 'Research decisions', 'Alerts']
  if (!portfolio?.latestNav) decisionFacts.push('Portfolio NAV')
  const groups = [
    { label: 'Provider', items: unique([...providerDomains, ...unavailableProviders]) },
    { label: 'Market Data', items: unique([...marketDomains, 'Market regime']) },
    { label: 'Decision Domain', items: unique(decisionFacts) },
  ].filter((group) => group.items.length)
  return (
    <AppShell currentPath="/">
      <PageHeading asOf={asOf} eyebrow="Decision workspace · API Mode" title="Today" summary="Current persisted facts, with unavailable domains left explicit." />
      <StateBoundary compact state={{
        kind: 'degraded',
        title: 'Some decision facts are unavailable',
        message: 'Available backend facts remain visible. No Fixture data was substituted.',
        groups,
      }}>
        <section className="terminal-section first-section" aria-labelledby="live-market-title">
          <div className="section-heading">
            <div><p className="section-kicker">External current market</p><h2 id="live-market-title">Market watchlist</h2></div>
            <span className="muted-copy">TradingView data is external current-market context · Not decision-time evidence</span>
          </div>
          <TradingViewTickerList symbols={quotes.map((quote) => quote.symbol)} />
          <details className="persisted-quote-evidence">
            <summary>Persisted quote evidence · {quotes.length} {quotes.length === 1 ? 'symbol' : 'symbols'}</summary>
            <p>PIT cutoff · {formatDualTime(asOf).newYork}</p>
            <ul aria-label="Persisted quote evidence">
              {quotes.map((quote) => <li key={quote.symbol}>
                <Link href={`/research/${quote.symbol}`}>{quote.symbol}</Link>
                <strong>{formatMoney(quote.close, 'USD')}</strong>
                <span>{quote.provider} · {quote.coverage}</span>
                <time dateTime={quote.availableAt}>Available {formatDualTime(quote.availableAt).newYork}</time>
              </li>)}
            </ul>
          </details>
        </section>
        <section className="terminal-section" aria-labelledby="paper-portfolio-title">
          <p className="section-kicker">Paper only</p><h2 id="paper-portfolio-title">Paper portfolio</h2>
          {portfolio?.latestNav
            ? <p><strong>{formatMoney(portfolio.latestNav.nav, 'USD')}</strong> at <time dateTime={portfolio.latestNav.eventTime}>{formatDualTime(portfolio.latestNav.eventTime).newYork}</time></p>
            : <p className="unavailable-value">No persisted NAV is available.</p>}
        </section>
      </StateBoundary>
    </AppShell>
  )
}

export function ApiResearchPage({
  asOf,
  dataQuality,
  financialFacts,
  quote,
  records,
  secFilings,
  symbol,
  unavailableDomains = [],
}: {
  asOf: string
  dataQuality: DataQuality[]
  financialFacts: FinancialFact[]
  quote: MarketQuote | null
  records: ResearchRecord[]
  secFilings: SecFiling[]
  symbol: string
  unavailableDomains?: string[]
}) {
  const missing = [
    ...unavailableDomains,
    ...(!quote ? ['Current market reference'] : []),
    ...(!records.length ? ['Research'] : []),
    ...(!secFilings.length ? ['SEC filings'] : []),
    ...(!financialFacts.length ? ['Fundamentals'] : []),
    'Earnings', 'News', 'Options', 'Analyst targets',
  ]
  const state = missing.length ? {
    kind: 'degraded' as const,
    title: records.length && !quote ? 'Current market reference unavailable' : 'Research evidence unavailable',
    message: 'Available persisted facts remain visible. No Fixture data was substituted.',
    providers: missing,
  } : { kind: 'success' as const }
  return (
    <AppShell currentPath={`/research/${symbol}`}>
      <PageHeading asOf={asOf} eyebrow="Research · API Mode" title={`${symbol} research`} summary="Persisted research only; current market reference remains separate from historical decision evidence." />
      <StateBoundary state={state}>
        {quote ? <section className="decision-hero" aria-label="Latest persisted market quote">
          <div><p className="section-kicker">Current market reference</p><h2>{quote.symbol}</h2><p className="thesis-copy">{formatMoney(quote.close, 'USD')}</p></div>
          <dl className="decision-facts"><div><dt>Provider</dt><dd>{quote.provider}</dd></div><div><dt>Coverage</dt><dd>{quote.coverage}</dd></div><div><dt>Available</dt><dd>{formatDualTime(quote.availableAt).newYork}</dd></div></dl>
        </section> : <p className="unavailable-value">Current quote unavailable.</p>}
        <p className="muted-copy">TradingView is a current-market reference only; it is not point-in-time decision evidence.</p>
        <TradingViewWidget kind="symbol-overview" symbol={symbol} />
        {records.map((record) => <article className="terminal-section" key={record.id}>
          <p className="section-kicker">Persisted thesis</p><h2>{record.direction}</h2><p>{record.summary}</p>
          <dl className="decision-facts"><div><dt>Opinion</dt><dd>{record.opinion ? <Signal tone={record.opinion}>{record.opinion}</Signal> : 'Unavailable'}</dd></div><div><dt>Confidence</dt><dd>{formatPercent(record.confidence, { signed: false })}</dd></div><div><dt>Horizon</dt><dd>{record.horizon}</dd></div></dl>
        </article>)}
        {secFilings.length ? <section className="terminal-section" aria-labelledby="sec-filings-heading">
          <p className="section-kicker">Persisted evidence</p><h2 id="sec-filings-heading">SEC filings</h2>
          <div className="table-scroll"><table><thead><tr><th>Form</th><th>Filed</th><th>Report period</th><th>Accession</th><th>Available</th><th>Raw source</th></tr></thead><tbody>
            {secFilings.map((filing) => <tr key={filing.id}><td>{filing.form}</td><td>{filing.filingDate}</td><td>{filing.reportDate ?? 'Unavailable'}</td><td>{filing.accessionNumber}</td><td>{formatDualTime(filing.availableAt).newYork}</td><td><code>{filing.documentRawObjectKey}</code></td></tr>)}
          </tbody></table></div>
        </section> : null}
        {financialFacts.length ? <section className="terminal-section" aria-labelledby="financial-facts-heading">
          <p className="section-kicker">Point-in-time fundamentals</p><h2 id="financial-facts-heading">Financial facts</h2>
          <div className="table-scroll"><table><thead><tr><th>Concept</th><th>Value</th><th>Period</th><th>Mapping</th><th>Accession</th><th>Available</th></tr></thead><tbody>
            {financialFacts.map((fact) => <tr key={fact.id}><td>{fact.canonicalConcept ?? fact.sourceConcept}</td><td>{formatDecimal(fact.value)} {fact.currency ?? fact.unit}</td><td>{fact.periodStart} — {fact.periodEnd}</td><td>{fact.mappingStatus}</td><td>{fact.accessionNumber}</td><td>{formatDualTime(fact.availableAt).newYork}</td></tr>)}
          </tbody></table></div>
        </section> : null}
        {dataQuality.length ? <section className="terminal-section" aria-labelledby="sec-quality-heading">
          <p className="section-kicker">Raw quality dimensions</p><h2 id="sec-quality-heading">SEC data quality</h2>
          <div className="table-scroll"><table><thead><tr><th>Dataset</th><th>Dimension</th><th>Status</th><th>Freshness</th><th>Delay</th><th>Conflict</th><th>Observed</th></tr></thead><tbody>
            {dataQuality.map((quality) => <tr key={quality.id}><td>{quality.dataset}</td><td>{quality.dimension}</td><td>{quality.status}</td><td>{quality.freshness ?? 'Unavailable'}</td><td>{quality.delay ?? 'Unavailable'}</td><td>{quality.conflict ? 'Yes' : 'No'}</td><td>{formatDualTime(quality.observedAt).newYork}</td></tr>)}
          </tbody></table></div>
        </section> : null}
      </StateBoundary>
    </AppShell>
  )
}

export function ApiPortfolioPage({ asOf, portfolio }: { asOf: string; portfolio: PortfolioSummary }) {
  const missing = [
    ...(!portfolio.latestNav ? ['NAV history'] : []),
    ...(!portfolio.positions.length ? ['Positions'] : []),
    ...(!portfolio.riskDecisions.length ? ['Risk decisions'] : []),
    ...(!portfolio.fills.length ? ['Paper fills'] : []),
  ]
  return (
    <AppShell currentPath="/portfolio">
      <PageHeading asOf={asOf} eyebrow="Simulate · API Mode" title="AI Portfolio" summary="Persisted paper-trading facts only. No live brokerage path exists." />
      <StateBoundary state={portfolio.status === 'EMPTY' ? {
        kind: 'empty',
        title: 'Paper portfolio not initialized',
        message: 'Initialize the approved singleton with USD 100,000. No Fixture portfolio was substituted.',
      } : missing.length ? {
        kind: 'degraded',
        title: 'Portfolio evidence is partial',
        message: 'Available authoritative paper facts remain visible; missing domains are not substituted.',
        providers: missing,
      } : {
        kind: 'success',
      }}>
        {portfolio.status === 'EMPTY' ? <form action={initializePortfolioAction}>
          <input name="effective_at" type="hidden" value={asOf} />
          <input name="idempotency_key" type="hidden" value={`portfolio-init:${asOf}`} />
          <button className="state-retry" type="submit">Initialize USD 100,000 paper portfolio</button>
        </form> : <section className="terminal-section first-section" aria-label="Paper portfolio summary">
          <p className="section-kicker">Paper portfolio</p>
          <h2>{portfolio.latestNav
            ? formatMoney(portfolio.latestNav.nav, 'USD')
            : portfolio.cash
              ? formatMoney(portfolio.cash.balance, portfolio.cash.currency)
              : 'Unavailable'}</h2>
          <p>{portfolio.latestNav
            ? <time dateTime={portfolio.latestNav.eventTime}>{formatDualTime(portfolio.latestNav.eventTime).newYork}</time>
            : 'Cash balance · no NAV snapshot yet'}</p>
        </section>}
      </StateBoundary>
    </AppShell>
  )
}

export function ApiWeeklyReviewPage({ asOf, detail }: { asOf: string; detail: WeeklyReviewDetail }) {
  const partial = !detail.outcomes.length
  return (
    <AppShell currentPath="/weekly-review">
      <PageHeading asOf={asOf} eyebrow="Learn · API Mode" title="Weekly Review" summary="Persisted outcomes and controlled-learning facts at the requested point-in-time cutoff." />
      <StateBoundary state={partial ? {
        kind: 'degraded',
        title: 'Weekly review has no matured outcomes',
        message: 'The persisted review remains visible; missing outcomes are not substituted.',
        providers: ['Matured outcomes'],
      } : { kind: 'success' }}>
        <section className="terminal-section first-section" aria-labelledby="weekly-outcomes-title">
          <p className="section-kicker">Measure</p><h2 id="weekly-outcomes-title">Outcome attribution</h2>
          <div className="table-scroll"><table aria-label="Persisted weekly outcomes"><thead><tr><th>Symbol</th><th>Opinion</th><th>Confidence</th><th>Return</th><th>Status</th></tr></thead><tbody>
            {detail.outcomes.map((outcome) => {
              const horizons = Object.keys(outcome.returns).sort((left, right) => Number(left) - Number(right))
              const realized = horizons.length ? outcome.returns[horizons[horizons.length - 1]] : null
              return <tr key={outcome.id}><th>{outcome.symbol}</th><td>{outcome.opinion}</td><td>{formatPercent(outcome.confidence, { signed: false })}</td><td>{realized ? formatPercent(realized) : 'Pending'}</td><td><Signal tone={outcome.status}>{outcome.status}</Signal></td></tr>
            })}
          </tbody></table></div>
        </section>
        <section className="terminal-section" aria-labelledby="weekly-calibration-title">
          <p className="section-kicker">Calibrate</p><h2 id="weekly-calibration-title">Confidence calibration</h2>
          <ul className="plain-list">{detail.calibration.map((item) => <li key={item.decisionId}><strong>{formatPercent(item.confidence, { signed: false })}</strong><p>{item.realizedReturn ? `Realized ${formatPercent(item.realizedReturn)}` : 'Outcome pending'} · error {formatPercent(item.calibrationError, { signed: false })}</p></li>)}</ul>
        </section>
        <section className="terminal-section" aria-labelledby="weekly-attribution-title">
          <p className="section-kicker">Attribute</p><h2 id="weekly-attribution-title">Error attribution</h2>
          <ul className="plain-list">{detail.attributions.map((item) => <li key={item.id}><strong>{item.category}</strong><p>{item.rationale}</p></li>)}</ul>
        </section>
        <section className="terminal-section" aria-labelledby="weekly-lessons-title">
          <p className="section-kicker">Control</p><h2 id="weekly-lessons-title">Candidate lessons</h2>
          <ul className="plain-list">{detail.lessons.map((lesson) => <li key={lesson.id}><strong>{lesson.status}</strong><p>{lesson.statement}</p><small>Confidence {formatPercent(lesson.confidence, { signed: false })} · replay delta {formatPercent(lesson.replayDelta)}</small></li>)}</ul>
        </section>
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
