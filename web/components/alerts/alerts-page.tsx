'use client'

import Link from 'next/link'
import { useState } from 'react'

import type { AlertsSnapshot } from '../../lib/product-types'
import { formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'

type Alert = AlertsSnapshot['alerts'][number]

function AlertCard({ alert }: { alert: Alert }) {
  return <li className="alert-summary-card">
    <div className="alert-card-head"><span>Severity <Signal tone={alert.severity}>{alert.severity}</Signal></span><span>Category <Signal tone={alert.category}>{alert.category}</Signal></span><strong>Scope {alert.symbol}</strong><span>Materiality {formatPercent(alert.materiality, { fractionDigits: 0, signed: false })}</span><time dateTime={alert.eventTime}>{formatDualTime(alert.eventTime).newYork}</time></div>
    <dl className="alert-scan-facts"><div><dt>Trigger</dt><dd>{alert.summary}</dd></div><div><dt>Acknowledgement</dt><dd>{alert.acknowledged ? 'Acknowledged' : 'Pending'}</dd></div></dl>
    <details aria-label={`Complete alert evidence for ${alert.symbol}`} className="route-secondary-disclosure alert-evidence-disclosure"><summary>Complete alert evidence</summary><div className="route-detail-content">
      <h3>{alert.summary}</h3><p className="review-action">{alert.reviewAction}</p>
      <dl className="alert-lineage"><div><dt>Thesis</dt><dd><Link href={`/research/${alert.symbol}`}>{alert.thesisId}</Link></dd></div><div><dt>Invalidation condition</dt><dd>{alert.invalidationConditionId}</dd></div><div><dt>Evidence</dt><dd>{alert.evidenceId}</dd></div><div><dt>Explanation</dt><dd><Signal tone={alert.explanation.status}>{alert.explanation.status}</Signal> {alert.explanation.detail}</dd></div></dl>
      <button aria-label={`Acknowledge alert ${alert.id}`} disabled type="button">Acknowledge alert</button><small>Disabled in frozen Fixture Mode.</small>
    </div></details>
  </li>
}

export function AlertsPage({ snapshot }: { snapshot: AlertsSnapshot }) {
  const [category, setCategory] = useState('ALL')
  const [severity, setSeverity] = useState('ALL')
  const categories = Array.from(new Set(snapshot.alerts.map((alert) => alert.category)))
  const severities = Array.from(new Set(snapshot.alerts.map((alert) => alert.severity)))
  const filtered = snapshot.alerts.filter((alert) => (
    (category === 'ALL' || alert.category === category)
    && (severity === 'ALL' || alert.severity === severity)
  ))
  const visible = filtered.slice(0, 4)
  const overflow = filtered.slice(4)

  return (
    <AppShell currentPath="/alerts">
      <PageHeading asOf={snapshot.asOf} eyebrow="Review" title="Alerts" summary="Deterministic anomaly rules surface attention; explanations never control delivery." />
      <FixtureNotice />
      <section className="terminal-section first-section route-critical-summary alert-triage-summary" aria-label="Alert triage summary">
        <div className="section-heading"><div><p className="section-kicker">Open queue</p><h2 id="alerts-page-title">Actionable alerts</h2></div><span className="muted-copy">{filtered.length} of {snapshot.alerts.length} unacknowledged fixture alerts</span></div>
        <div className="alert-filters" aria-label="Alert filters">
          <label><span>Severity</span><select aria-label="Filter by severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="ALL">All severities</option>{severities.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <label><span>Category</span><select aria-label="Filter by category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="ALL">All categories</option>{categories.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        </div>
        {visible.length === 0 ? <p role="status">No alerts match the selected filters.</p> : <ol aria-label="Actionable alert queue" className="alert-cards alert-comparison-grid">{visible.map((alert) => <AlertCard alert={alert} key={alert.id} />)}</ol>}
      </section>
      {overflow.length ? <details aria-label="Complete alert queue" className="route-secondary-disclosure complete-alert-queue"><summary>Complete alert queue · {overflow.length} additional</summary><ol className="alert-cards alert-comparison-grid">{overflow.map((alert) => <AlertCard alert={alert} key={alert.id} />)}</ol></details> : null}
    </AppShell>
  )
}
