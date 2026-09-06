import Link from 'next/link'

import type { ResearchSnapshot } from '../../lib/product-types'
import { formatPercent } from '../../lib/format'
import { formatDualTime, parseAwareInstant } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { TradingViewWidget } from '../market/tradingview-widget'
import { FixtureNotice, PageHeading, QualityFacts, Signal } from '../ui/product-ui'

export function ResearchPage({ snapshot }: { snapshot: ResearchSnapshot }) {
  const freshestEvidenceAt = snapshot.lineage
    .map((item) => item.evidence.availableAt)
    .sort((left, right) => parseAwareInstant(left).getTime() - parseAwareInstant(right).getTime())
    .at(-1) ?? snapshot.asOf

  return (
    <AppShell currentPath={`/research/${snapshot.symbol}`}>
      <PageHeading asOf={snapshot.asOf} eyebrow="Research" title={`${snapshot.symbol} research`} summary="A decision record whose conclusions stay attached to evidence, gaps, and provenance." />
      <FixtureNotice />
      <section className="decision-hero research-conclusion" aria-label={`${snapshot.symbol} research conclusion`}>
        <div><p className="section-kicker">Latest conclusion · {snapshot.symbol}</p><h2 id="thesis-title">Investment thesis</h2><p className="thesis-copy">{snapshot.thesis.summary}</p><p className="muted-copy">Report <strong>{snapshot.report.id}</strong> · <time dateTime={snapshot.report.generatedAt}>{formatDualTime(snapshot.report.generatedAt).newYork}</time></p><p className="research-freshness"><span>Evidence freshness</span><time dateTime={freshestEvidenceAt}>{formatDualTime(freshestEvidenceAt).newYork}</time></p></div>
        <dl className="decision-facts"><div><dt>Research opinion</dt><dd><Signal tone={snapshot.researchOpinion}>{snapshot.researchOpinion}</Signal></dd></div><div><dt>Portfolio action</dt><dd><Signal tone={snapshot.portfolioAction}>{snapshot.portfolioAction}</Signal></dd></div><div><dt>Confidence</dt><dd>{formatPercent(snapshot.thesis.confidence, { signed: false })}</dd></div><div><dt>Horizon</dt><dd>{snapshot.thesis.horizon}</dd></div></dl>
      </section>
      <TradingViewWidget kind="symbol-overview" symbol={snapshot.symbol} />
      <section className="research-domain-grid" aria-label="Point-in-time research evidence">
        <section aria-labelledby="fundamentals-title"><h2 id="fundamentals-title">Fundamentals</h2><dl>{snapshot.fundamentals.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}<small>{fact.source}</small></dd></div>)}</dl></section>
        <section aria-labelledby="earnings-title"><h2 id="earnings-title">Earnings</h2>{snapshot.earnings.map((item) => <div key={item.period}><strong>{item.period}</strong><p>{item.summary}</p><time dateTime={item.reportedAt}>{formatDualTime(item.reportedAt).newYork}</time></div>)}</section>
        <section aria-labelledby="news-title"><h2 id="news-title">News</h2>{snapshot.news.map((item) => <div key={item.headline}><strong>{item.headline}</strong><p>{item.provider}</p><time dateTime={item.eventTime}>{formatDualTime(item.eventTime).newYork}</time></div>)}</section>
        <section aria-labelledby="options-title"><h2 id="options-title">Options</h2><Signal tone={snapshot.options.status}>{snapshot.options.status}</Signal><p>{snapshot.options.summary}</p></section>
        <section aria-labelledby="analyst-targets-title"><h2 id="analyst-targets-title">Analyst targets</h2><dl><div><dt>Consensus</dt><dd>{snapshot.analystTargets.consensus}</dd></div><div><dt>Target price</dt><dd>{snapshot.analystTargets.targetPrice}</dd></div></dl><p>{snapshot.analystTargets.provider} · <time dateTime={snapshot.analystTargets.asOf}>{formatDualTime(snapshot.analystTargets.asOf).newYork}</time></p></section>
      </section>
      <div className="research-grid">
        <section className="terminal-section" aria-labelledby="lineage-title">
          <div className="section-heading"><div><p className="section-kicker">Prove</p><h2 id="lineage-title">Claim to source lineage</h2></div><Link href="/runs/latest">Open run trace</Link></div>
          <ol className="lineage-list">{snapshot.lineage.map((item) => <li key={item.claim.id}>
            <div className="lineage-step"><span>Claim</span><strong>{item.claim.id}</strong><p>{item.claim.statement}</p></div>
            <div className="lineage-step"><Signal tone={item.evidence.relation}>{item.evidence.relation}</Signal><strong>{item.evidence.id}</strong><p>{item.evidence.summary}</p><QualityFacts quality={item.evidence.dataQuality} /></div>
            <div className="lineage-step"><span>ToolCall</span><strong>{item.toolCall.id}</strong><p>{item.toolCall.name} · {item.evidence.provider}</p><p className="time-label">New York · <time dateTime={item.evidence.availableAt}>{formatDualTime(item.evidence.availableAt).newYork}</time></p></div>
          </li>)}</ol>
        </section>
        <aside className="research-rail">
          <section aria-labelledby="invalidation-title"><p className="section-kicker">Monitor</p><h2 id="invalidation-title">Invalidation conditions</h2><ul className="plain-list">{snapshot.invalidationConditions.map((condition) => <li key={condition}>{condition}</li>)}</ul></section>
          <section aria-labelledby="gaps-title"><p className="section-kicker">Uncertainty</p><h2 id="gaps-title">Evidence gaps</h2><ul className="plain-list">{snapshot.gaps.map((gap) => <li key={`${gap.kind}-${gap.domain}`}><Signal tone={gap.kind}>{gap.kind}</Signal><strong>{gap.domain}</strong><p>{gap.reason}</p></li>)}</ul></section>
        </aside>
      </div>
      <div className="research-grid lower-grid">
        <section className="terminal-section" aria-labelledby="diff-title"><p className="section-kicker">Change</p><h2 id="diff-title">Decision diff</h2><p className="muted-copy">Deterministic comparison with the prior immutable decision.</p><dl className="diff-list">{snapshot.decisionDiff.map((diff) => <div key={diff.field}><dt>{diff.field.replace('_', ' ')}</dt><dd><s>{diff.from}</s><span aria-hidden="true">→</span><strong>{diff.to}</strong><span className="sr-only">{diff.field} changed from {diff.from} to {diff.to}</span></dd></div>)}</dl></section>
        <section className="terminal-section" aria-labelledby="pins-title"><p className="section-kicker">Reproduce</p><h2 id="pins-title">Frozen policy versions</h2><dl className="pin-list">{snapshot.policyPins.map((pin) => <div key={pin.label}><dt>{pin.label}</dt><dd>{pin.version}</dd></div>)}</dl></section>
      </div>
      <section className="terminal-section" aria-labelledby="decision-history-title">
        <p className="section-kicker">History</p><h2 id="decision-history-title">Decision history</h2>
        <div className="table-scroll"><table aria-label="Immutable decision history" tabIndex={0}><thead><tr><th scope="col">Decision</th><th scope="col">As of</th><th scope="col">Research opinion</th><th scope="col">Portfolio action</th><th scope="col">Confidence</th></tr></thead><tbody>{snapshot.decisionHistory.map((decision) => <tr key={decision.id}><th scope="row">{decision.id}</th><td><time dateTime={decision.asOf}>{formatDualTime(decision.asOf).newYork}</time></td><td><Signal tone={decision.researchOpinion}>{decision.researchOpinion}</Signal></td><td><Signal tone={decision.portfolioAction}>{decision.portfolioAction}</Signal></td><td>{formatPercent(decision.confidence, { signed: false })}</td></tr>)}</tbody></table></div>
      </section>
    </AppShell>
  )
}
