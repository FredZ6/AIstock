import Link from 'next/link'

import type { AlertsSnapshot } from '../../lib/product-types'
import { formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'

export function AlertsPage({ snapshot }: { snapshot: AlertsSnapshot }) {
  return (
    <AppShell currentPath="/alerts">
      <PageHeading asOf={snapshot.asOf} eyebrow="Review" title="Alerts" summary="Deterministic anomaly rules surface attention; explanations never control delivery." />
      <FixtureNotice />
      <section className="terminal-section first-section" aria-labelledby="alerts-page-title"><div className="section-heading"><div><p className="section-kicker">Open queue</p><h2 id="alerts-page-title">Actionable alerts</h2></div><span className="muted-copy">{snapshot.alerts.length} unacknowledged fixture alert</span></div><ol className="alert-cards">{snapshot.alerts.map((alert) => <li key={alert.id}>
        <div className="alert-card-head"><Signal tone={alert.severity}>{alert.severity}</Signal><Signal tone={alert.category}>{alert.category}</Signal><strong>{alert.symbol}</strong><span>Materiality {formatPercent(alert.materiality, { fractionDigits: 0, signed: false })}</span><time dateTime={alert.eventTime}>{formatDualTime(alert.eventTime).newYork}</time></div>
        <h3>{alert.summary}</h3><p className="review-action">{alert.reviewAction}</p>
        <dl className="alert-lineage"><div><dt>Thesis</dt><dd><Link href={`/research/${alert.symbol}`}>{alert.thesisId}</Link></dd></div><div><dt>Invalidation condition</dt><dd>{alert.invalidationConditionId}</dd></div><div><dt>Evidence</dt><dd>{alert.evidenceId}</dd></div><div><dt>Explanation</dt><dd><Signal tone={alert.explanation.status}>{alert.explanation.status}</Signal> {alert.explanation.detail}</dd></div></dl>
        <button aria-label={`Acknowledge alert ${alert.id}`} disabled type="button">Acknowledge alert</button><small>Disabled in frozen Fixture Mode.</small>
      </li>)}</ol></section>
    </AppShell>
  )
}
