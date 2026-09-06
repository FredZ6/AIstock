import type { EvalAdminSnapshot } from '../../lib/product-types'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'

export function EvalAdminPage({ snapshot }: { snapshot: EvalAdminSnapshot }) {
  return (
    <AppShell currentPath="/eval">
      <PageHeading asOf={snapshot.asOf} eyebrow="Govern" title="Eval & Admin" summary="Inspect frozen controls and release boundaries without silently changing production state." />
      <FixtureNotice />
      <section className="operational-evidence" aria-label="Operational evidence">
        <section aria-label="Evaluation report status">
          {snapshot.evaluation ? <div className="terminal-section first-section"><div className="section-heading"><div><p className="section-kicker">Measured evidence</p><h2>Offline evaluation report</h2></div><Signal tone={snapshot.evaluation.passed ? 'healthy' : 'failure'}>{snapshot.evaluation.passed ? 'PASS' : 'FAIL'}</Signal></div><dl className="metric-list"><div><dt>Dataset</dt><dd>{snapshot.evaluation.datasetVersion}</dd></div><div><dt>Cases</dt><dd>{snapshot.evaluation.caseCount} cases</dd></div><div><dt>Mode</dt><dd>{snapshot.evaluation.mode}</dd></div><div><dt>Gate policy</dt><dd>{snapshot.evaluation.policyVersion}</dd></div></dl><div className="table-scroll"><table aria-label="Measured evaluation metrics"><thead><tr><th scope="col">Metric</th><th scope="col">Measured value</th></tr></thead><tbody>{snapshot.evaluation.metrics.map((metric) => <tr key={metric.label}><th scope="row">{metric.label}</th><td>{metric.value}</td></tr>)}</tbody></table></div><p className="muted-copy">Raw artifact: <code>{snapshot.evaluation.artifactPath}</code>. Values come from the frozen evaluation runner; they are not live-market or production claims.</p></div> : <div className="scope-callout" role="note"><p className="section-kicker">Measured evidence unavailable</p><h2>Offline evaluation report unavailable</h2><p>Run <code>make evaluate</code> or <code>make smoke</code>. No metric is substituted or invented when the raw artifact is absent.</p></div>}
        </section>
        <div className="operations-status-grid">
          <section aria-label="Regression comparison"><span>Regression comparison</span><strong className="unavailable-value">Unavailable</strong><p>No baseline comparison exists in the current evaluation artifact.</p></section>
          <section aria-label="Provider health"><span>Provider health</span><strong className="unavailable-value">Unavailable</strong><p>Provider runtime health is outside this frozen evaluation snapshot.</p></section>
        </div>
        <section aria-label="Policy state">
          <div className="terminal-section" aria-labelledby="policies-title"><div className="section-heading"><div><p className="section-kicker">Policy control</p><h2 id="policies-title">Pinned policy versions</h2></div><span className="muted-copy">Read-only Fixture Mode</span></div><div className="table-scroll"><table aria-label="Pinned policy versions" tabIndex={0}><thead><tr><th scope="col">Policy</th><th scope="col">Version</th><th scope="col">State</th><th scope="col">Activation boundary</th></tr></thead><tbody>{snapshot.policyVersions.map((policy) => <tr key={policy.kind}><th scope="row">{policy.kind}</th><td>{policy.version}</td><td><Signal tone={policy.active ? 'healthy' : 'stale'}>{policy.active ? 'ACTIVE' : 'INACTIVE'}</Signal></td><td>Human authorization required · automatic activation is disabled</td></tr>)}</tbody></table></div></div>
        </section>
      </section>
    </AppShell>
  )
}
