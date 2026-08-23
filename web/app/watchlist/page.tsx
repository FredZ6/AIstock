import {
  ApiWatchlistPage,
  WatchlistFailurePage,
  WatchlistPage,
} from '../../components/watchlist/watchlist-page'
import { readApiBaseUrl, readWebDataMode } from '../../lib/server/data-mode'
import { listWatchlist } from '../../lib/server/watchlist-api'

export const dynamic = 'force-dynamic'

export default async function WatchlistRoute() {
  try {
    const mode = readWebDataMode(process.env)
    if (mode === 'fixture') {
      const { fixtureWatchlistSnapshot } = await import('../../lib/fixtures')
      return <WatchlistPage snapshot={fixtureWatchlistSnapshot} />
    }

    const items = await listWatchlist({ baseUrl: readApiBaseUrl(process.env) })
    return <ApiWatchlistPage items={items} />
  } catch {
    return <WatchlistFailurePage asOf={new Date().toISOString()} />
  }
}
