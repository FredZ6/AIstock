import { ApiFailurePage, ApiTodayPage } from '../components/live/api-pages'
import { TodayPage } from '../components/today-page'
import { readWebDataConfig } from '../lib/server/data-mode'
import { getMarketQuotes, getPortfolioSummary, getProviderHealth } from '../lib/server/live-data-api'
import { listWatchlist } from '../lib/server/watchlist-api'

export const dynamic = 'force-dynamic'

export default async function Home() {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { fixtureTodaySnapshot } = await import('../lib/api')
      return <TodayPage snapshot={fixtureTodaySnapshot} />
    }
    const decisionTime = new Date().toISOString()
    const options = { baseUrl: config.baseUrl, decisionTime }
    const watchlist = await listWatchlist({ baseUrl: config.baseUrl })
    const [health, portfolio, quotes] = await Promise.all([
      getProviderHealth(options),
      getPortfolioSummary(options),
      watchlist.length
        ? getMarketQuotes(options, watchlist.map((item) => item.symbol))
        : Promise.resolve({ decisionTime, items: [], status: 'FAILURE' as const }),
    ])
    return <ApiTodayPage asOf={decisionTime} health={health} portfolio={portfolio} quotes={quotes.items} />
  } catch {
    return <ApiFailurePage currentPath="/" title="Today" />
  }
}
