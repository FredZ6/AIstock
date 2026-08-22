import Link from 'next/link'

import type { WatchlistSnapshot } from '../../lib/product-types'
import { formatMoney, formatPercent } from '../../lib/format'
import { formatDualTime } from '../../lib/time'
import { AppShell } from '../layout/app-shell'
import { FixtureNotice, PageHeading, QualityFacts, Signal } from '../ui/product-ui'

export function WatchlistPage({ snapshot }: { snapshot: WatchlistSnapshot }) {
  return (
    <AppShell currentPath="/watchlist">
      <PageHeading asOf={snapshot.asOf} eyebrow="Discover" title="Watchlist" summary="Rank attention without turning uncertainty into a trading instruction." />
      <FixtureNotice />
      <section className="terminal-section first-section" aria-labelledby="watchlist-count">
        <div className="section-heading"><div><p className="section-kicker">Research universe</p><h2 id="watchlist-count">{snapshot.symbols.length} of {snapshot.limit} symbols</h2></div><span className="muted-copy">Long-only US technology equities</span></div>
        <div className="table-scroll">
          <table aria-label="Research watchlist">
            <thead><tr><th scope="col">Symbol</th><th scope="col">Price</th><th scope="col">Day</th><th scope="col">Research opinion</th><th scope="col">Portfolio action</th><th scope="col">Last research</th><th scope="col">Data quality</th></tr></thead>
            <tbody>{snapshot.symbols.map((item) => <tr key={item.symbol}>
              <th scope="row"><Link href={`/research/${item.symbol}`}>{item.symbol}</Link></th>
              <td>{formatMoney(item.price, 'USD')}</td><td>{formatPercent(item.dailyReturn)}</td>
              <td><Signal tone={item.researchOpinion}>{item.researchOpinion}</Signal></td>
              <td><Signal tone={item.portfolioAction}>{item.portfolioAction}</Signal></td>
              <td><time dateTime={item.lastResearchAt}>{formatDualTime(item.lastResearchAt).newYork}</time></td>
              <td><QualityFacts quality={item.dataQuality} /></td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>
    </AppShell>
  )
}
