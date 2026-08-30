import {
  ApiWatchlistPage,
  WatchlistFailurePage,
  WatchlistPage,
} from '../../components/watchlist/watchlist-page'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { getMarketQuotes } from '../../lib/server/live-data-api'
import { listWatchlist } from '../../lib/server/watchlist-api'

export const dynamic = 'force-dynamic'

export default async function WatchlistRoute() {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { fixtureWatchlistSnapshot } = await import('../../lib/fixtures')
      return <WatchlistPage snapshot={fixtureWatchlistSnapshot} />
    }

    const items = await listWatchlist({ baseUrl: config.baseUrl })
    const decisionTime = new Date().toISOString()
    const quotes = items.length
      ? await getMarketQuotes(
        { baseUrl: config.baseUrl, decisionTime },
        items.map((item) => item.symbol),
      ).catch(() => ({ items: [], missingSymbols: items.map((item) => item.symbol) }))
      : { items: [], missingSymbols: [] }
    const asOf = items.reduce(
      (latest, item) => item.updatedAt > latest ? item.updatedAt : latest,
      items[0]?.updatedAt ?? new Date().toISOString(),
    )
    return <ApiWatchlistPage asOf={asOf} items={items} missingSymbols={quotes.missingSymbols} quotes={quotes.items} />
  } catch {
    return <WatchlistFailurePage asOf={new Date().toISOString()} />
  }
}
