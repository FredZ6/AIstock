import Link from 'next/link'

import { AppShell } from './layout/app-shell'
import { PerformanceChart } from './portfolio/performance-chart'
import { StateBoundary } from './states/state-boundary'
import { TodayDashboard, TodayDashboardHeader } from './today/today-dashboard'
import type { TodayDashboardModel } from './today/today-dashboard-model'
import { type TodaySnapshot } from '../lib/api'
import { formatMoney, formatPercent } from '../lib/format'
import { formatDualTime } from '../lib/time'
import { Signal } from './ui/product-ui'

type TodayPageProps = {
  snapshot: TodaySnapshot
}

export function TodayPage({ snapshot }: TodayPageProps) {
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

  const model: TodayDashboardModel = {
    mode: 'fixture',
    asOf: snapshot.asOf,
    heading: {
      eyebrow: 'Decision workspace',
      title: 'Today',
      summary: 'What changed, what needs attention, and what the system can prove.',
      notice: { label: 'Fixture Mode', description: 'Frozen synthetic fixture · not current market data' },
    },
    portfolio: { kind: 'available', value: <PerformanceChart compact snapshot={{ ...snapshot.portfolio, asOf: snapshot.asOf }} /> },
    marketRegime: { kind: 'available', value: <>
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
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{formatPercent(value)}</dd></div>)}
        </dl>
      </section>
    </> },
    watchlist: { kind: 'available', value: {
      kicker: 'Discover', title: 'Watchlist signals', action: <Link className="compact-hit-link" href="/watchlist">Manage watchlist</Link>,
      content: <ul className="watchlist-heatmap market-list" aria-label="Watchlist signals">
        {snapshot.watchlist.map((item) => <li key={item.symbol} data-direction={item.dailyReturn.startsWith('-') ? 'negative' : 'positive'}>
          <div className="heatmap-primary"><Link className="compact-hit-link" href={`/research/${item.symbol}`}>{item.symbol}</Link><strong>{formatPercent(item.dailyReturn)}</strong></div>
          <span>{formatMoney(item.price, 'USD')}</span>
          <div className="heatmap-decisions"><Signal tone={item.researchOpinion.toLowerCase()}>{item.researchOpinion}</Signal><Signal tone={item.portfolioAction.toLowerCase()}>{item.portfolioAction}</Signal></div>
          <div className="quality-line"><span>{item.dataQuality.freshness}</span><span>{formatPercent(item.dataQuality.coverage, { fractionDigits: 0, signed: false })} coverage</span><span>{item.dataQuality.provider}</span><span>{item.dataQuality.delaySeconds}s delay</span><span>{item.dataQuality.conflict ? 'Conflict detected' : 'No conflict'}</span></div>
        </li>)}
      </ul>,
    } },
    alerts: snapshot.alerts.length ? { kind: 'available', value: {
      kicker: 'Decide', title: 'Actionable alerts', action: <Link className="compact-hit-link" href="/alerts">View all</Link>,
      content: <ul className="alert-list">{snapshot.alerts.slice(0, 3).map((alert) => <li key={alert.id}>
        <div className="alert-meta"><Signal tone={alert.severity.toLowerCase()}>{alert.severity}</Signal><Link className="compact-hit-link" href={`/research/${alert.symbol}`}>{alert.symbol}</Link><time dateTime={alert.eventTime}>{formatDualTime(alert.eventTime).newYork}</time></div>
        <p>{alert.summary}</p><strong>{alert.reviewAction}</strong>
      </li>)}</ul>,
    } } : { kind: 'empty', message: 'No actionable alerts.' },
    activeRun: snapshot.activeRun ? { kind: 'available', value: {
      kicker: 'Run progress', title: 'Research execution',
      content: <div className="run-progress"><div><Link className="compact-hit-link" href={`/runs/${snapshot.activeRun.id}`}>{snapshot.activeRun.label}</Link><span>{snapshot.activeRun.status}</span></div><progress aria-label={snapshot.activeRun.label} max={snapshot.activeRun.totalSteps} value={snapshot.activeRun.completedSteps} /><p>{snapshot.activeRun.completedSteps} of {snapshot.activeRun.totalSteps} steps</p></div>,
    } } : { kind: 'empty', message: 'No active run.' },
  }

  return (
    <AppShell currentPath="/">
      <div className="today-page">
        <TodayDashboardHeader model={model} />

        <StateBoundary compact state={state}>
          <div className="today-content">
            <TodayDashboard model={model} />

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
