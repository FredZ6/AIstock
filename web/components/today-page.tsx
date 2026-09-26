import Link from 'next/link'

import { AppShell } from './layout/app-shell'
import { PerformanceChart } from './portfolio/performance-chart'
import { StateBoundary } from './states/state-boundary'
import { type TodaySnapshot } from '../lib/api'
import { formatMoney, formatPercent } from '../lib/format'
import { formatDualTime } from '../lib/time'
import { Signal } from './ui/product-ui'

type TodayPageProps = {
  snapshot: TodaySnapshot
}

export function TodayPage({ snapshot }: TodayPageProps) {
  const times = formatDualTime(snapshot.asOf)
  const degradedProviders = snapshot.providers
    .filter((provider) => provider.status !== 'HEALTHY')
    .map((provider) => provider.label)
  const state = degradedProviders.length
    ? {
        kind: 'degraded' as const,
        title: 'Provider coverage degraded',
        message: 'Available facts remain visible. Review provider and data-quality labels before acting.',
        providers: degradedProviders,
      }
    : { kind: 'success' as const }

  return (
    <AppShell currentPath="/">
      <div className="today-page">
        <header className="today-heading">
          <div>
            <p className="eyebrow">Decision workspace</p>
            <h1>Today</h1>
            <p className="today-summary">What changed, what needs attention, and what the system can prove.</p>
          </div>
          <div className="today-meta">
            <div className="time-context" aria-label="Snapshot time">
              <p>
                <span>New York</span>
                <time dateTime={snapshot.asOf}>{times.newYork}</time>
              </p>
              <p>
                <span>Shanghai</span>
                <time dateTime={snapshot.asOf}>{times.shanghai}</time>
              </p>
            </div>
            <div className="fixture-notice" role="note">
              <strong>Fixture Mode</strong>
              <span>Frozen synthetic fixture · not current market data</span>
            </div>
          </div>
        </header>

        <StateBoundary compact state={state}>
          <div className="today-content">
            <section aria-label="Today decision workspace" className="today-decision-workspace">
              <section className="market-portfolio-grid surface-card" aria-label="Market and portfolio summary">
                <div aria-label="Portfolio overview" className="portfolio-summary portfolio-overview" role="region">
                  <PerformanceChart compact snapshot={{ ...snapshot.portfolio, asOf: snapshot.asOf }} />
                </div>

                <div aria-label="Market regime" className="market-regime market-regime-compact" role="region">
                  <p className="section-kicker">Market regime</p>
                  <div className="regime-title" data-testid="regime-metadata">
                    <Signal tone="positive">{snapshot.marketRegime.label}</Signal>
                    <span className="algorithm-version"><small>Model</small><span>{snapshot.marketRegime.algorithmVersion}</span></span>
                  </div>
                  <dl className="metric-list compact">
                    <div><dt>QQQ trend</dt><dd>{formatPercent(snapshot.marketRegime.qqqTrend)}</dd></div>
                    <div><dt>QQQ volatility</dt><dd>{formatPercent(snapshot.marketRegime.qqqVolatility, { signed: false })}</dd></div>
                    <div><dt>SOXX relative strength</dt><dd>{formatPercent(snapshot.marketRegime.soxxRelativeStrength)}</dd></div>
                    <div><dt>VIX</dt><dd>{snapshot.marketRegime.vix}</dd></div>
                  </dl>
                  <section className="benchmark-pulse" aria-labelledby="benchmark-pulse-title">
                    <h3 id="benchmark-pulse-title">Benchmark pulse</h3>
                    <dl aria-label="Portfolio benchmarks">
                      {[
                        ['Cash', snapshot.portfolio.benchmarks.cash],
                        ['QQQ', snapshot.portfolio.benchmarks.qqq],
                        ['Equal weight', snapshot.portfolio.benchmarks.equalWeight],
                        ['Momentum', snapshot.portfolio.benchmarks.momentum],
                      ].map(([label, value]) => (
                        <div key={label}><dt>{label}</dt><dd>{formatPercent(value)}</dd></div>
                      ))}
                    </dl>
                  </section>
                </div>
              </section>

              <section className="terminal-section today-watchlist" aria-labelledby="watchlist-title">
                <div className="section-heading">
                  <div><p className="section-kicker">Discover</p><h2 id="watchlist-title">Watchlist signals</h2></div>
                  <Link className="compact-hit-link" href="/watchlist">Manage watchlist</Link>
                </div>
                <ul className="watchlist-heatmap market-list" aria-label="Watchlist signals">
                  {snapshot.watchlist.map((item) => (
                    <li key={item.symbol} data-direction={item.dailyReturn.startsWith('-') ? 'negative' : 'positive'}>
                      <div className="heatmap-primary"><Link className="compact-hit-link" href={`/research/${item.symbol}`}>{item.symbol}</Link><strong>{formatPercent(item.dailyReturn)}</strong></div>
                      <span>{formatMoney(item.price, 'USD')}</span>
                      <div className="heatmap-decisions"><Signal tone={item.researchOpinion.toLowerCase()}>{item.researchOpinion}</Signal><Signal tone={item.portfolioAction.toLowerCase()}>{item.portfolioAction}</Signal></div>
                      <div className="quality-line"><span>{item.dataQuality.freshness}</span><span>{formatPercent(item.dataQuality.coverage, { fractionDigits: 0, signed: false })} coverage</span><span>{item.dataQuality.provider}</span><span>{item.dataQuality.delaySeconds}s delay</span><span>{item.dataQuality.conflict ? 'Conflict detected' : 'No conflict'}</span></div>
                    </li>
                  ))}
                </ul>
              </section>

              <section aria-label="Decision activity" className="decision-activity">
                <section className="terminal-section" aria-labelledby="alerts-title">
                  <div className="section-heading">
                    <div><p className="section-kicker">Decide</p><h2 id="alerts-title">Actionable alerts</h2></div>
                    <Link className="compact-hit-link" href="/alerts">View all</Link>
                  </div>
                  <ul className="alert-list">
                    {snapshot.alerts.slice(0, 3).map((alert) => (
                      <li key={alert.id}>
                        <div className="alert-meta">
                          <Signal tone={alert.severity.toLowerCase()}>{alert.severity}</Signal>
                          <Link className="compact-hit-link" href={`/research/${alert.symbol}`}>{alert.symbol}</Link>
                          <time dateTime={alert.eventTime}>{formatDualTime(alert.eventTime).newYork}</time>
                        </div>
                        <p>{alert.summary}</p>
                        <strong>{alert.reviewAction}</strong>
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="operations-rail research-activity" aria-labelledby="run-title">
                  <p className="section-kicker">Run progress</p><h2 id="run-title">Research execution</h2>
                  {snapshot.activeRun ? (
                    <div className="run-progress">
                      <div><Link className="compact-hit-link" href={`/runs/${snapshot.activeRun.id}`}>{snapshot.activeRun.label}</Link><span>{snapshot.activeRun.status}</span></div>
                      <progress aria-label={snapshot.activeRun.label} max={snapshot.activeRun.totalSteps} value={snapshot.activeRun.completedSteps} />
                      <p>{snapshot.activeRun.completedSteps} of {snapshot.activeRun.totalSteps} steps</p>
                    </div>
                  ) : <p>No active run</p>}
                </section>
              </section>
            </section>

            <details aria-label="Provider diagnostics" className="provider-diagnostics">
              <summary>Provider diagnostics</summary>
              <section aria-labelledby="providers-title">
                <p className="section-kicker">Data plane</p><h2 id="providers-title">Provider health</h2>
                <ul className="provider-list">
                  {snapshot.providers.map((provider) => (
                    <li key={provider.id}><span>{provider.label}</span><Signal tone={provider.status.toLowerCase()}>{provider.status}</Signal><small>{provider.mode.replace('_', ' ')}</small></li>
                  ))}
                </ul>
              </section>
            </details>
          </div>
        </StateBoundary>
      </div>
    </AppShell>
  )
}
