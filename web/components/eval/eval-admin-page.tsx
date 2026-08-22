import type { EvalAdminSnapshot } from '../../lib/product-types'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'

export function EvalAdminPage({ snapshot }: { snapshot: EvalAdminSnapshot }) {
  return (
    <AppShell currentPath="/eval">
      <PageHeading asOf={snapshot.asOf} eyebrow="Govern" title="Eval & Admin" summary="Inspect frozen controls and release boundaries without silently changing production state." />
      <FixtureNotice />
      <section className="scope-callout" role="note"><p className="section-kicker">Milestone boundary</p><h2>Evaluation is intentionally limited</h2><p>Task 16 evaluation gates have not started. This page exposes current policy lineage only; no future metric is presented as implemented.</p></section>
      <section className="terminal-section" aria-labelledby="policies-title"><div className="section-heading"><div><p className="section-kicker">Policy control</p><h2 id="policies-title">Pinned policy versions</h2></div><span className="muted-copy">Read-only Fixture Mode</span></div><div className="table-scroll"><table aria-label="Pinned policy versions" tabIndex={0}><thead><tr><th scope="col">Policy</th><th scope="col">Version</th><th scope="col">State</th><th scope="col">Activation boundary</th></tr></thead><tbody>{snapshot.policyVersions.map((policy) => <tr key={policy.kind}><th scope="row">{policy.kind}</th><td>{policy.version}</td><td><Signal tone={policy.active ? 'healthy' : 'stale'}>{policy.active ? 'ACTIVE' : 'INACTIVE'}</Signal></td><td>Human authorization required · automatic activation is disabled</td></tr>)}</tbody></table></div></section>
    </AppShell>
  )
}
