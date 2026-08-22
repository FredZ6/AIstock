import type { PortfolioSnapshot } from '../../lib/product-types'
import { formatMoney, formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { TradingViewWidget } from '../market/tradingview-widget'
import { FixtureNotice, PageHeading, Signal } from '../ui/product-ui'
import { PerformanceChart } from './performance-chart'

export function PortfolioPage({ snapshot }: { snapshot: PortfolioSnapshot }) {
  return (
    <AppShell currentPath="/portfolio">
      <PageHeading asOf={snapshot.asOf} eyebrow="Simulate" title="AI Portfolio" summary="Deterministic risk and execution around immutable research decisions. Paper Trading only." />
      <FixtureNotice />
      <PerformanceChart snapshot={snapshot} />
      <section className="portfolio-cash" aria-label="Portfolio cash"><span>Available cash</span><strong>{formatMoney(snapshot.cash, snapshot.currency)}</strong><small>Derived from the append-only CashLedger fixture.</small></section>
      <figure aria-labelledby="benchmark-title" className="benchmark-figure benchmark-panel"><figcaption id="benchmark-title"><span className="section-kicker">Frozen comparison</span><strong>Benchmark comparison</strong></figcaption><div className="benchmark-bars">{snapshot.benchmarks.map((benchmark) => <div key={benchmark.label}><span>{benchmark.label}</span><span className="bar-track" aria-hidden="true"><span style={{ width: `${Math.max(6, Number(benchmark.return) * 10000)}%` }} /></span><strong>{formatPercent(benchmark.return)}</strong></div>)}</div></figure>
      <section className="terminal-section" aria-labelledby="positions-title"><div className="section-heading"><div><p className="section-kicker">Holdings</p><h2 id="positions-title">Positions</h2></div><span className="muted-copy">Actions remain separate from research opinions</span></div><div className="table-scroll"><table aria-label="Paper portfolio positions" tabIndex={0}><thead><tr><th scope="col">Symbol</th><th scope="col">Quantity</th><th scope="col">Market value</th><th scope="col">Unrealized P&amp;L</th><th scope="col">Weight</th><th scope="col">Portfolio action</th></tr></thead><tbody>{snapshot.positions.map((position) => <tr key={position.symbol}><th scope="row">{position.symbol}</th><td>{position.quantity}</td><td>{formatMoney(position.marketValue, snapshot.currency)}</td><td>{formatMoney(position.unrealizedPnl, snapshot.currency)}</td><td>{formatPercent(position.weight, { signed: false })}</td><td><Signal tone={position.action}>{position.action}</Signal></td></tr>)}</tbody></table></div><div className="mini-chart-grid">{snapshot.positions.map((position) => <TradingViewWidget key={position.symbol} kind="mini-chart" symbol={position.symbol} />)}</div></section>
      <section className="portfolio-evidence-grid" aria-label="Paper trading evidence">
        <article><h2>Risk decisions</h2><div className="table-scroll"><table aria-label="Risk decisions" tabIndex={0}><thead><tr><th scope="col">Decision</th><th scope="col">Intent</th><th scope="col">Status</th><th scope="col">Reason</th></tr></thead><tbody>{snapshot.riskDecisions.map((decision) => <tr key={decision.id}><th scope="row">{decision.id}</th><td>{decision.orderIntentId}</td><td><Signal tone={decision.status}>{decision.status}</Signal></td><td>{decision.reason}</td></tr>)}</tbody></table></div></article>
        <article><h2>Paper fills</h2><div className="table-scroll"><table aria-label="Paper fills" tabIndex={0}><thead><tr><th scope="col">Fill</th><th scope="col">Order</th><th scope="col">Symbol</th><th scope="col">Quantity</th><th scope="col">Price</th><th scope="col">Time</th></tr></thead><tbody>{snapshot.fills.map((fill) => <tr key={fill.id}><th scope="row">{fill.id}</th><td>{fill.orderId}</td><td>{fill.symbol}</td><td>{fill.quantity}</td><td>{formatMoney(fill.price, snapshot.currency)}</td><td><time dateTime={fill.eventTime}>{formatDualTime(fill.eventTime).newYork}</time></td></tr>)}</tbody></table></div></article>
        <article><h2>Cash ledger</h2><div className="table-scroll"><table aria-label="Cash ledger" tabIndex={0}><thead><tr><th scope="col">Entry</th><th scope="col">Kind</th><th scope="col">Amount</th><th scope="col">Balance</th><th scope="col">Time</th></tr></thead><tbody>{snapshot.cashLedger.map((entry) => <tr key={entry.id}><th scope="row">{entry.id}</th><td>{entry.kind}</td><td>{formatMoney(entry.amount, snapshot.currency)}</td><td>{formatMoney(entry.balance, snapshot.currency)}</td><td><time dateTime={entry.eventTime}>{formatDualTime(entry.eventTime).newYork}</time></td></tr>)}</tbody></table></div></article>
      </section>
      <section className="execution-strip" aria-label="Execution and ledger controls"><div><span>Fill timing</span><strong>{snapshot.execution.fillTiming}</strong></div><div><span>Execution policy</span><strong>{snapshot.execution.policyVersion}</strong></div><div><span>Accounting</span><strong>{snapshot.execution.ledgerStatus}</strong></div></section>
    </AppShell>
  )
}
