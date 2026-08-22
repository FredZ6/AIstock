import type { PortfolioSnapshot } from '../../lib/product-types'
import { formatMoney, formatPercent } from '../../lib/format'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'

export function PortfolioPage({ snapshot }: { snapshot: PortfolioSnapshot }) {
  return (
    <AppShell currentPath="/portfolio">
      <PageHeading asOf={snapshot.asOf} eyebrow="Simulate" title="AI Portfolio" summary="Deterministic risk and execution around immutable research decisions. Paper Trading only." />
      <FixtureNotice />
      <section className="portfolio-hero" aria-label="Paper portfolio summary">
        <div><p className="section-kicker">Net asset value</p><p className="nav-value">{formatMoney(snapshot.nav, snapshot.currency)}</p><p className="portfolio-inline"><span>Day {formatPercent(snapshot.dayReturn)}</span><span>Drawdown {formatPercent(snapshot.drawdown)}</span></p></div>
        <figure aria-labelledby="benchmark-title" className="benchmark-figure"><figcaption id="benchmark-title"><span className="section-kicker">Chart summary</span><strong>Benchmark comparison</strong></figcaption><div className="benchmark-bars">{snapshot.benchmarks.map((benchmark) => <div key={benchmark.label}><span>{benchmark.label}</span><span className="bar-track" aria-hidden="true"><span style={{ width: `${Math.max(6, Number(benchmark.return) * 10000)}%` }} /></span><strong>{formatPercent(benchmark.return)}</strong></div>)}</div><p>Momentum leads the frozen one-day comparison; Cash remains the zero-return baseline.</p></figure>
      </section>
      <section className="terminal-section" aria-labelledby="positions-title"><div className="section-heading"><div><p className="section-kicker">Holdings</p><h2 id="positions-title">Positions</h2></div><span className="muted-copy">Actions remain separate from research opinions</span></div><div className="table-scroll"><table aria-label="Paper portfolio positions"><thead><tr><th scope="col">Symbol</th><th scope="col">Quantity</th><th scope="col">Market value</th><th scope="col">Weight</th><th scope="col">Portfolio action</th></tr></thead><tbody>{snapshot.positions.map((position) => <tr key={position.symbol}><th scope="row">{position.symbol}</th><td>{position.quantity}</td><td>{formatMoney(position.marketValue, snapshot.currency)}</td><td>{formatPercent(position.weight, { signed: false })}</td><td><Signal tone={position.action}>{position.action}</Signal></td></tr>)}</tbody></table></div></section>
      <section className="execution-strip" aria-label="Execution and ledger controls"><div><span>Fill timing</span><strong>{snapshot.execution.fillTiming}</strong></div><div><span>Execution policy</span><strong>{snapshot.execution.policyVersion}</strong></div><div><span>Accounting</span><strong>{snapshot.execution.ledgerStatus}</strong></div></section>
    </AppShell>
  )
}
