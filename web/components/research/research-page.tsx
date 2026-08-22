import Link from 'next/link'

import type { ResearchSnapshot } from '../../lib/product-types'
import { formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, QualityFacts, Signal } from '../ui/product-ui'

export function ResearchPage({ snapshot }: { snapshot: ResearchSnapshot }) {
  return (
    <AppShell currentPath={`/research/${snapshot.symbol}`}>
      <PageHeading asOf={snapshot.asOf} eyebrow="Research" title={`${snapshot.symbol} research`} summary="A decision record whose conclusions stay attached to evidence, gaps, and provenance." />
      <FixtureNotice />
      <section className="decision-hero" aria-labelledby="thesis-title">
        <div><p className="section-kicker">Investment thesis</p><h2 id="thesis-title">Investment thesis</h2><p className="thesis-copy">{snapshot.thesis.summary}</p></div>
        <dl className="decision-facts"><div><dt>Research opinion</dt><dd><Signal tone={snapshot.researchOpinion}>{snapshot.researchOpinion}</Signal></dd></div><div><dt>Portfolio action</dt><dd><Signal tone={snapshot.portfolioAction}>{snapshot.portfolioAction}</Signal></dd></div><div><dt>Confidence</dt><dd>{formatPercent(snapshot.thesis.confidence, { signed: false })}</dd></div><div><dt>Horizon</dt><dd>{snapshot.thesis.horizon}</dd></div></dl>
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
    </AppShell>
  )
}
