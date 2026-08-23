import {
  ApiWatchlistPage,
  WatchlistFailurePage,
  WatchlistPage,
} from '../../components/watchlist/watchlist-page'
import { readWebDataConfig } from '../../lib/server/data-mode'
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
    return <ApiWatchlistPage items={items} />
  } catch {
    return <WatchlistFailurePage asOf={new Date().toISOString()} />
  }
}
