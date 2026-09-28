import { AppShell } from './layout/app-shell'
import { StateBoundary } from './states/state-boundary'
import { TodayDashboard, TodayDashboardHeader } from './today/today-dashboard'
import type { TodayDashboardModel } from './today/today-dashboard-model'
import { Signal } from './ui/product-ui'
import { type TodaySnapshot } from '../lib/api'
import { formatMoney, formatPercent } from '../lib/format'

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
    portfolio: { kind: 'available', value: { snapshot: { ...snapshot.portfolio, asOf: snapshot.asOf } } },
    marketRegime: { kind: 'available', value: {
      label: snapshot.marketRegime.label,
      model: snapshot.marketRegime.algorithmVersion,
      tone: 'positive',
      metrics: [
        { label: 'QQQ trend', value: formatPercent(snapshot.marketRegime.qqqTrend) },
        { label: 'QQQ volatility', value: formatPercent(snapshot.marketRegime.qqqVolatility, { signed: false }) },
        { label: 'SOXX relative strength', value: formatPercent(snapshot.marketRegime.soxxRelativeStrength) },
        { label: 'VIX', value: snapshot.marketRegime.vix },
      ],
      benchmarks: [
        { label: 'Cash', value: formatPercent(snapshot.portfolio.benchmarks.cash) },
        { label: 'QQQ', value: formatPercent(snapshot.portfolio.benchmarks.qqq) },
        { label: 'Equal weight', value: formatPercent(snapshot.portfolio.benchmarks.equalWeight) },
        { label: 'Momentum', value: formatPercent(snapshot.portfolio.benchmarks.momentum) },
      ],
    } },
    watchlist: { kind: 'available', value: {
      kicker: 'Discover', title: 'Watchlist signals', action: { href: '/watchlist', label: 'Manage watchlist' },
      items: snapshot.watchlist.map((item) => ({
        symbol: item.symbol,
        direction: item.dailyReturn.startsWith('-') ? 'negative' : 'positive',
        primaryValue: formatPercent(item.dailyReturn),
        detail: formatMoney(item.price, 'USD'),
        decisions: [
          { label: item.researchOpinion, tone: item.researchOpinion },
          { label: item.portfolioAction, tone: item.portfolioAction },
        ],
        provenance: [item.dataQuality.freshness, `${formatPercent(item.dataQuality.coverage, { fractionDigits: 0, signed: false })} coverage`, item.dataQuality.provider, `${item.dataQuality.delaySeconds}s delay`, item.dataQuality.conflict ? 'Conflict detected' : 'No conflict'],
      })),
    } },
    alerts: snapshot.alerts.length ? { kind: 'available', value: {
      kicker: 'Decide', title: 'Actionable alerts', action: { href: '/alerts', label: 'View all' },
      items: snapshot.alerts.slice(0, 3).map((alert) => ({ id: alert.id, severity: alert.severity, symbol: alert.symbol, eventTime: alert.eventTime, detail: alert.summary, emphasis: alert.reviewAction })),
    } } : { kind: 'empty', message: 'No actionable alerts.' },
    activeRun: snapshot.activeRun ? { kind: 'available', value: {
      href: `/runs/${snapshot.activeRun.id}`,
      label: snapshot.activeRun.label,
      status: snapshot.activeRun.status,
      completedSteps: snapshot.activeRun.completedSteps,
      totalSteps: snapshot.activeRun.totalSteps,
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
