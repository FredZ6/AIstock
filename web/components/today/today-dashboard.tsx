import type { TodayDashboardModel, TodaySlot } from './today-dashboard-model'
import { formatDualTime } from '../../lib/time'
import { TodayWatchlistSection } from './today-watchlist-section'

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
        {model.portfolio.kind === 'available' ? model.portfolio.value : <SlotFallback slot={model.portfolio} />}
      </div>
      <div aria-label="Market regime" className="market-regime market-regime-compact" role="region">
        {model.marketRegime.kind === 'available' ? model.marketRegime.value : <>
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
          <div className="section-heading"><div><p className="section-kicker">{model.alerts.value.kicker}</p><h2 id="alerts-title">{model.alerts.value.title}</h2></div>{model.alerts.value.action}</div>
          {model.alerts.value.content}
        </> : <><p className="section-kicker">Decide</p><h2>Actionable alerts</h2><SlotFallback slot={model.alerts} /></>}
      </section>
      <section aria-label="Research execution" className="operations-rail research-activity" role="region">
        {model.activeRun.kind === 'available' ? <>
          <p className="section-kicker">{model.activeRun.value.kicker}</p><h2 id="run-title">{model.activeRun.value.title}</h2>{model.activeRun.value.action}
          {model.activeRun.value.content}
        </> : <><p className="section-kicker">Run progress</p><h2>Research execution</h2><SlotFallback slot={model.activeRun} /></>}
      </section>
    </section>
  </section>
}
