import {
  ApiWatchlistPage,
  WatchlistFailurePage,
  WatchlistPage,
} from '../../components/watchlist/watchlist-page'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { getHistoricalBars, getMarketQuotes, getStockResearch } from '../../lib/server/live-data-api'
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
    const historyStart = new Date(Date.parse(decisionTime) - 45 * 24 * 60 * 60 * 1000).toISOString()
    const quotes = items.length
      ? await getMarketQuotes(
        { baseUrl: config.baseUrl, decisionTime },
        items.map((item) => item.symbol),
      ).catch((error) => {
        reportLiveDataFailure('/watchlist', 'market-quotes', error)
        return { items: [], missingSymbols: items.map((item) => item.symbol), status: 'FAILURE' as const }
      })
      : { items: [], missingSymbols: [], status: 'SUCCESS' as const }
    const enrichments = await Promise.all(items.map(async (item) => {
      const [history, research] = await Promise.allSettled([
        getHistoricalBars({ baseUrl: config.baseUrl, decisionTime }, item.symbol, historyStart, decisionTime),
        getStockResearch({ baseUrl: config.baseUrl, decisionTime }, item.symbol),
      ])
      if (history.status === 'rejected') reportLiveDataFailure('/watchlist', `${item.symbol}-market-history`, history.reason)
      if (research.status === 'rejected') reportLiveDataFailure('/watchlist', `${item.symbol}-earnings`, research.reason)
      return {
        earnings: research.status === 'fulfilled' && !research.value.unavailableDomains.includes('EARNINGS')
          ? research.value.earningsEvents
          : null,
        history: history.status === 'fulfilled' ? history.value.items : null,
        symbol: item.symbol,
      }
    }))
    return <ApiWatchlistPage
      asOf={decisionTime}
      earningsBySymbol={Object.fromEntries(enrichments.flatMap((item) => item.earnings === null ? [] : [[item.symbol, item.earnings]]))}
      historiesBySymbol={Object.fromEntries(enrichments.flatMap((item) => item.history === null ? [] : [[item.symbol, item.history]]))}
      items={items}
      missingSymbols={quotes.missingSymbols}
      quoteStatus={quotes.status}
      quotes={quotes.items}
    />
  } catch (error) {
    reportLiveDataFailure('/watchlist', 'watchlist', error)
    return <WatchlistFailurePage asOf={new Date().toISOString()} />
  }
}
