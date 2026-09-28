import type { TodayDashboardModel, TodaySlot } from './today-dashboard-model'
import { formatDualTime } from '../../lib/time'
import { TodayWatchlistSection } from './today-watchlist-section'
import Link from 'next/link'
import { PerformanceChart } from '../portfolio/performance-chart'
import { Signal } from '../ui/product-ui'

function SlotFallback({ slot }: { slot: Exclude<TodaySlot<unknown>, { kind: 'available' }> }) {
  return <p className="unavailable-value" data-slot-state={slot.kind}>{slot.message}</p>
}

export function TodayDashboardHeader({ model }: { model: TodayDashboardModel }) {
  const times = formatDualTime(model.asOf)
  return <header className="today-heading">
    <div>
      <p className="eyebrow">{model.heading.eyebrow}</p>
      <h1>{model.heading.title}</h1>
      <p className="today-summary">{model.heading.summary}</p>
    </div>
    <div className="today-meta">
      <div className="time-context" aria-label="Snapshot time">
        <p><span>New York</span><time dateTime={model.asOf}>{times.newYork}</time></p>
        <p><span>Shanghai</span><time dateTime={model.asOf}>{times.shanghai}</time></p>
      </div>
      <div className="fixture-notice" data-mode={model.mode} role="note">
        <strong>{model.heading.notice.label}</strong>
        <span>{model.heading.notice.description}</span>
      </div>
    </div>
  </header>
}

export function TodayDashboard({ model }: { model: TodayDashboardModel }) {
  return <section aria-label="Today decision workspace" className="today-decision-workspace">
    <section className="market-portfolio-grid surface-card" aria-label="Market and portfolio summary">
      <div aria-label="Portfolio overview" className="portfolio-summary portfolio-overview" role="region">
        {model.portfolio.kind === 'available' ? <PerformanceChart compact historySource={model.portfolio.value.historySource} snapshot={model.portfolio.value.snapshot} /> : <SlotFallback slot={model.portfolio} />}
      </div>
      <div aria-label="Market regime" className="market-regime market-regime-compact" role="region">
        {model.marketRegime.kind === 'available' ? <>
          <p className="section-kicker">Market regime</p>
          <div className="regime-title" data-testid="regime-metadata"><Signal tone={model.marketRegime.value.tone}>{model.marketRegime.value.label}</Signal><span className="algorithm-version"><small>Model</small><span>{model.marketRegime.value.model}</span></span></div>
          <dl className="metric-list compact">{model.marketRegime.value.metrics.map((metric) => <div key={metric.label}><dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}</dl>
          {model.marketRegime.value.benchmarks?.length ? <section className="benchmark-pulse" aria-labelledby="benchmark-pulse-title"><h3 id="benchmark-pulse-title">Benchmark pulse</h3><dl aria-label="Portfolio benchmarks">{model.marketRegime.value.benchmarks.map((benchmark) => <div key={benchmark.label}><dt>{benchmark.label}</dt><dd>{benchmark.value}</dd></div>)}</dl></section> : null}
        </> : <>
          <p className="section-kicker">Market regime</p>
          <h2>Market regime unavailable</h2>
          <SlotFallback slot={model.marketRegime} />
        </>}
      </div>
    </section>

    {model.watchlist.kind === 'available'
      ? <TodayWatchlistSection mode={model.mode} panel={model.watchlist.value} />
      : <section aria-label="Watchlist signals" className="terminal-section today-watchlist">
        <p className="section-kicker">Discover</p><h2>Watchlist signals</h2>
        <SlotFallback slot={model.watchlist} />
      </section>}

    <section aria-label="Decision activity" className="decision-activity">
      <section className="terminal-section" aria-label="Actionable alerts">
        {model.alerts.kind === 'available' ? <>
          <div className="section-heading"><div><p className="section-kicker">{model.alerts.value.kicker}</p><h2 id="alerts-title">{model.alerts.value.title}</h2></div>{model.alerts.value.action ? <Link className="compact-hit-link" href={model.alerts.value.action.href}>{model.alerts.value.action.label}</Link> : null}</div>
          <ul className="alert-list">{model.alerts.value.items.map((alert) => <li key={alert.id}><div className="alert-meta"><Signal tone={alert.severity}>{alert.severity}</Signal><Link className="compact-hit-link" href={`/research/${alert.symbol}`}>{alert.symbol}</Link><time dateTime={alert.eventTime}>{formatDualTime(alert.eventTime).newYork}</time></div><p>{alert.detail}</p>{alert.emphasis ? <strong>{alert.emphasis}</strong> : null}</li>)}</ul>
        </> : <><p className="section-kicker">Decide</p><h2>Actionable alerts</h2><SlotFallback slot={model.alerts} /></>}
      </section>
      <section aria-label="Research execution" className="operations-rail research-activity" role="region">
        {model.activeRun.kind === 'available' ? <>
          <p className="section-kicker">Run progress</p><h2 id="run-title">Research execution</h2>
          <div className="run-progress"><div><Link className="compact-hit-link" href={model.activeRun.value.href}>{model.activeRun.value.label}</Link><Signal tone={model.activeRun.value.status}>{model.activeRun.value.status}</Signal></div>{model.activeRun.value.completedSteps !== undefined && model.activeRun.value.totalSteps !== undefined ? <><progress aria-label={model.activeRun.value.label} max={model.activeRun.value.totalSteps} value={model.activeRun.value.completedSteps} /><p>{model.activeRun.value.completedSteps} of {model.activeRun.value.totalSteps} steps</p></> : model.activeRun.value.decisionTime ? <p>Decision time <time dateTime={model.activeRun.value.decisionTime}>{formatDualTime(model.activeRun.value.decisionTime).newYork}</time></p> : null}</div>
        </> : <><p className="section-kicker">Run progress</p><h2>Research execution</h2><SlotFallback slot={model.activeRun} /></>}
      </section>
    </section>
  </section>
}
