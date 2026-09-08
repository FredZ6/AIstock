import type { RunTraceSnapshot } from '../../lib/product-types'
import { formatMoney } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'

export function RunTracePage({ snapshot }: { snapshot: RunTraceSnapshot }) {
  const elapsedMs = snapshot.events.reduce((total, event) => total + Number(event.durationMs), 0)
  const currentStep = snapshot.events.findLast((event) => event.status === 'RUNNING') ?? snapshot.events.at(-1)
  const retries = snapshot.events.filter((event) => event.status === 'RETRYING').length
  const degradations = snapshot.events.filter((event) => event.status === 'FALLBACK').length
  const checkpoints = snapshot.events.filter((event) => event.type === 'checkpoint.saved').length

  return (
    <AppShell currentPath="/runs/latest">
      <PageHeading asOf={snapshot.asOf} eyebrow="Audit" title={`Research run · ${snapshot.symbol}`} summary="Durable execution facts, ordered as persisted—not reconstructed from transient logs." />
      <FixtureNotice />
      <section className="run-overview" aria-label="Run operations summary">
        <div><p className="section-kicker">Status</p><Signal tone={snapshot.status}>{snapshot.status}</Signal><small>{snapshot.runId}</small></div>
        <div>
          <dl className="run-progress-facts"><div><dt>Elapsed</dt><dd>{elapsedMs.toLocaleString('en-US')} ms</dd></div><div><dt>Current step</dt><dd>{currentStep?.detail ?? 'No event persisted'}</dd></div><div><dt>Retries</dt><dd>{retries}</dd></div><div><dt>Degradations</dt><dd>{degradations}</dd></div><div><dt>Checkpoints</dt><dd>{checkpoints}</dd></div><div><dt>Data cutoff</dt><dd><time dateTime={snapshot.asOf}>{formatDualTime(snapshot.asOf).newYork}</time></dd></div></dl>
          <dl className="budget-strip"><div><dt>LLM calls</dt><dd>{snapshot.budgets.llmCalls.used} of {snapshot.budgets.llmCalls.limit} LLM calls</dd></div><div><dt>Tool calls</dt><dd>{snapshot.budgets.toolCalls.used} of {snapshot.budgets.toolCalls.limit} tool calls</dd></div><div><dt>Tokens</dt><dd>{snapshot.budgets.tokens.toLocaleString('en-US')} tokens</dd></div><div><dt>Recorded cost</dt><dd>{formatMoney(snapshot.budgets.costUsd, 'USD')}</dd></div></dl>
        </div>
      </section>
      <section className="terminal-section first-section" aria-labelledby="events-title">
        <div className="section-heading"><div><p className="section-kicker">Sequence</p><h2 id="events-title">Durable event trace</h2></div><span className="muted-copy">Resume with Last-Event-ID · {snapshot.lastEventId}</span></div>
        <ol aria-label="Durable run events" className="trace-list">{snapshot.events.map((event) => <li key={event.id}>
          <span className="trace-sequence">{String(event.sequence).padStart(2, '0')}</span>
          <div><div className="trace-title"><strong>{event.type}</strong><Signal tone={event.status}>{event.status}</Signal></div><p>{event.detail}</p><small>{event.id} · <span>{new Intl.NumberFormat('en-US').format(Number(event.durationMs))} ms</span> · <time dateTime={event.eventTime}>{formatDualTime(event.eventTime).newYork}</time></small></div>
        </li>)}</ol>
      </section>
    </AppShell>
  )
}
