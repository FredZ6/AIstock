import type { WeeklyReviewSnapshot } from '../../lib/product-types'
import { formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'

export function WeeklyReviewPage({ snapshot }: { snapshot: WeeklyReviewSnapshot }) {
  return (
    <AppShell currentPath="/weekly-review">
      <PageHeading asOf={snapshot.asOf} eyebrow="Learn" title="Weekly Review" summary="Attribute outcomes, replay the past honestly, and keep every policy change under human control." />
      <FixtureNotice />
      <section className="terminal-section first-section weekly-outcome-summary" aria-label="Weekly outcome summary">
        <div className="section-heading"><div><p className="section-kicker">Measure</p><h2>Weekly outcome summary</h2></div><span className="unavailable-value">Benchmark comparison unavailable in this frozen snapshot</span></div>
        <h3>Outcome attribution</h3><div className="outcome-strip">{snapshot.outcomes.map((outcome) => <div key={`${outcome.symbol}-${outcome.horizon}`}><strong>{outcome.symbol}</strong><span>{outcome.horizon}</span><b>{formatPercent(outcome.return)}</b></div>)}</div>
        <h3>Thesis outcomes</h3><div className="table-scroll" tabIndex={0}><table aria-label="Thesis outcomes"><thead><tr><th scope="col">Symbol</th><th scope="col">Horizon</th><th scope="col">Confidence</th><th scope="col">Result</th></tr></thead><tbody>{snapshot.outcomes.map((outcome) => <tr key={`${outcome.symbol}-thesis`}><th scope="row">{outcome.symbol}</th><td>{outcome.horizon}</td><td>{formatPercent(outcome.confidence, { signed: false })}</td><td><Signal tone={outcome.thesisHit}>{outcome.thesisHit}</Signal></td></tr>)}</tbody></table></div>
        <h3 id="calibration-title">Confidence calibration</h3><p className="muted-copy">Descriptive frozen buckets only; Task 16 owns formal Brier and ECE gates.</p><div className="table-scroll" tabIndex={0}><table aria-label="Confidence calibration"><thead><tr><th scope="col">Confidence bucket</th><th scope="col">Decisions</th><th scope="col">Observed thesis hit rate</th></tr></thead><tbody>{snapshot.calibration.map((bucket) => <tr key={bucket.bucket}><th scope="row">{bucket.bucket}</th><td>{bucket.decisionCount}</td><td>{formatPercent(bucket.observedHitRate, { signed: false })}</td></tr>)}</tbody></table></div>
      </section>
      <div className="review-grid">
        <section className="terminal-section" aria-labelledby="attribution-title"><p className="section-kicker">Attribute</p><h2 id="attribution-title">Error attribution</h2><ul className="plain-list">{snapshot.attribution.map((item) => <li key={item.category}><strong>{item.category}</strong><p>{item.detail}</p></li>)}</ul></section>
        <section className="terminal-section replay-panel" aria-labelledby="replay-title"><p className="section-kicker">Verify</p><h2 id="replay-title">Point-in-time replay</h2><p>{snapshot.replay.result}</p><dl><div><dt>Historical cutoff</dt><dd><time dateTime={snapshot.replay.availableAtCutoff}>{formatDualTime(snapshot.replay.availableAtCutoff).newYork}</time></dd></div><div><dt>Counterfactual score delta</dt><dd>{snapshot.replay.scoreDelta}</dd></div></dl></section>
      </div>
      <section className="lesson-panel" aria-label="Candidate lesson"><div><p className="section-kicker">Candidate lesson</p><h2 id="lesson-title">{snapshot.lesson.id}</h2><p>{snapshot.lesson.proposal}</p><Signal tone={snapshot.lesson.status}>{snapshot.lesson.status}</Signal></div><div className="approval-panel"><strong>Human decision boundary</strong><p>Unapproved activation rejected. Human approval was recorded, but the candidate remains inactive; automatic activation is disabled.</p><div><button disabled type="button">Approve candidate lesson</button><button disabled type="button">Reject candidate lesson</button></div><small>Fixture Mode is read-only.</small></div></section>
    </AppShell>
  )
}
