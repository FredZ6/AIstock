'use client'

import Link from 'next/link'
import { useState } from 'react'

import { formatPercent } from '../../lib/format'
import type { AlertRecord } from '../../lib/server/live-data-api'
import { formatDualTime } from '../../lib/time'
import { Signal } from '../ui/product-ui'

type AlertCategory = 'PRICE' | 'VOLUME' | 'OPTIONS' | 'EARNINGS' | 'NEWS' | 'ANALYST_TARGET' | 'PORTFOLIO_RISK'

function categoryFor(alert: AlertRecord): AlertCategory {
  const rule = alert.ruleId.toLowerCase()
  if (rule.includes('volume')) return 'VOLUME'
  if (rule.includes('option')) return 'OPTIONS'
  if (rule.includes('earning')) return 'EARNINGS'
  if (rule.includes('news')) return 'NEWS'
  if (rule.includes('target') || rule.includes('analyst')) return 'ANALYST_TARGET'
  if (rule.includes('portfolio') || rule.includes('risk')) return 'PORTFOLIO_RISK'
  return 'PRICE'
}

function alertEvidence(value: unknown) {
  return JSON.stringify(value, null, 2)
}

function ApiAlertCard({ alert }: { alert: AlertRecord }) {
  const category = categoryFor(alert)
  return <li className="alert-summary-card" id={`alert-${alert.id}`}>
    <div className="alert-card-head">
      <span>Severity <Signal tone={alert.severity}>{alert.severity}</Signal></span>
      <span>Category <Signal tone={category}>{category}</Signal></span>
      <strong><Link href={`/research/${alert.symbol}`} aria-label={`${alert.symbol} research`}>{alert.symbol}</Link></strong>
      <span>Materiality {formatPercent(alert.materiality, { signed: false })}</span>
      <time dateTime={alert.eventTime}>{formatDualTime(alert.eventTime).newYork}</time>
    </div>
    <dl className="alert-scan-facts"><div><dt>Trigger</dt><dd>{alert.ruleId} · {alert.ruleVersion}</dd></div><div><dt>Acknowledgement</dt><dd>{alert.acknowledgedAt ? 'Acknowledged' : 'Not acknowledged'}</dd></div></dl>
    <details aria-label={`Complete alert evidence for ${alert.symbol}`} className="route-secondary-disclosure alert-evidence-disclosure"><summary>Complete alert evidence</summary><div className="route-detail-content">
      <dl className="decision-facts">
        <div><dt>Event time</dt><dd><time dateTime={alert.eventTime}>{formatDualTime(alert.eventTime).newYork}</time></dd></div>
        <div><dt>Recorded</dt><dd><time dateTime={alert.createdAt}>{formatDualTime(alert.createdAt).newYork}</time></dd></div>
        <div><dt>Acknowledgement</dt><dd>{alert.acknowledgedAt ? <><time dateTime={alert.acknowledgedAt}>{formatDualTime(alert.acknowledgedAt).newYork}</time> · {alert.acknowledgedBy}</> : 'Not acknowledged'}</dd></div>
        <div><dt>Alert key</dt><dd><code>{alert.alertKey}</code></dd></div>
      </dl>
      <div><h4>Conditions, metrics, and data quality</h4><div className="decision-facts">
        <div><dt>Conditions</dt><dd><pre>{alertEvidence(alert.conditions)}</pre></dd></div>
        <div><dt>Metrics</dt><dd><pre>{alertEvidence(alert.metrics)}</pre></dd></div>
        <div><dt>Data quality</dt><dd><pre>{alertEvidence(alert.dataQuality)}</pre></dd></div>
      </div></div>
      <p><small>Correlation ID · <code>{alert.correlationId}</code></small></p>
      <p><Link href="/runs/latest">Open latest run trace</Link></p>
    </div></details>
  </li>
}

export function ApiAlertsQueue({ alerts, asOf }: { alerts: AlertRecord[]; asOf: string }) {
  const [category, setCategory] = useState('ALL')
  const [severity, setSeverity] = useState('ALL')
  const categories = Array.from(new Set(alerts.map(categoryFor)))
  const severities = Array.from(new Set(alerts.map((alert) => alert.severity)))
  const filtered = alerts.filter((alert) => (
    (category === 'ALL' || categoryFor(alert) === category)
    && (severity === 'ALL' || alert.severity === severity)
  ))
  const visible = filtered.slice(0, 4)
  const overflow = filtered.slice(4)

  return <>
    <section className="terminal-section first-section route-critical-summary alert-triage-summary" aria-label="Alert triage summary">
      <div className="section-heading"><div><p className="section-kicker">Persisted records</p><h2 id="persisted-alerts-title">Alert stream</h2></div><span className="muted-copy">PIT cutoff · {formatDualTime(asOf).newYork}</span></div>
      <div className="alert-filters" aria-label="Alert filters">
        <label><span>Severity</span><select aria-label="Filter by severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="ALL">All severities</option>{severities.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label><span>Category</span><select aria-label="Filter by category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="ALL">All categories</option>{categories.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      </div>
      {visible.length === 0 ? <p role="status">No alerts match the selected filters.</p> : <ol aria-label="Actionable alert queue" className="alert-cards alert-comparison-grid">{visible.map((alert) => <ApiAlertCard alert={alert} key={alert.id} />)}</ol>}
    </section>
    {overflow.length ? <details aria-label="Complete alert queue" className="route-secondary-disclosure complete-alert-queue"><summary>Complete alert queue · {overflow.length} additional</summary><ol className="alert-cards alert-comparison-grid">{overflow.map((alert) => <ApiAlertCard alert={alert} key={alert.id} />)}</ol></details> : null}
  </>
}
