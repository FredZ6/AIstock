import { ApiFailurePage, ApiTodayPage } from '../components/live/api-pages'
import { TodayPage } from '../components/today-page'
import { readWebDataConfig } from '../lib/server/data-mode'
import { reportLiveDataFailure } from '../lib/server/live-data-diagnostics'
import {
  getAlerts,
  getMarketQuotes,
  getPortfolioSummary,
  getProviderHealth,
  getStockResearch,
} from '../lib/server/live-data-api'
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
    const [watchlistResult, healthResult, portfolioResult, alertsResult] = await Promise.allSettled([
      listWatchlist({ baseUrl: config.baseUrl }),
      getProviderHealth(options),
      getPortfolioSummary(options),
      getAlerts(options),
    ])
    if (watchlistResult.status === 'rejected') reportLiveDataFailure('/', 'watchlist', watchlistResult.reason)
    if (healthResult.status === 'rejected') reportLiveDataFailure('/', 'provider-health', healthResult.reason)
    if (portfolioResult.status === 'rejected') reportLiveDataFailure('/', 'portfolio', portfolioResult.reason)
    if (alertsResult.status === 'rejected') reportLiveDataFailure('/', 'alerts', alertsResult.reason)
    const watchlist = watchlistResult.status === 'fulfilled' ? watchlistResult.value : []
    const quotesResult = watchlistResult.status === 'fulfilled' && watchlist.length === 0
      ? { status: 'fulfilled' as const, value: { items: [], missingSymbols: [], status: 'SUCCESS' as const } }
      : watchlist.length
      ? await getMarketQuotes(options, watchlist.map((item) => item.symbol)).then(
        (value) => ({ status: 'fulfilled' as const, value }),
        (error) => {
          reportLiveDataFailure('/', 'market-quotes', error)
          return { status: 'rejected' as const }
        },
      )
      : { status: 'rejected' as const }
    const researchResults = await Promise.allSettled(
      watchlist.map((item) => getStockResearch(options, item.symbol)),
    )
    researchResults.forEach((result, index) => {
      if (result.status === 'rejected') {
        reportLiveDataFailure('/', `${watchlist[index].symbol}-research`, result.reason)
      }
    })
    const research = researchResults.flatMap((result) =>
      result.status === 'fulfilled' ? result.value.records : [],
    )
    const availableFacts = [healthResult, portfolioResult, quotesResult, alertsResult]
      .some((result) => result.status === 'fulfilled')
    if (!availableFacts) return <ApiFailurePage currentPath="/" title="Today" />
    const unavailableDomains = [
      ...(watchlistResult.status === 'rejected' ? ['Watchlist API'] : []),
      ...(healthResult.status === 'rejected' ? ['Provider health'] : []),
      ...(portfolioResult.status === 'rejected' ? ['Portfolio API'] : []),
      ...(alertsResult.status === 'rejected' ? ['Alerts API'] : []),
      ...(quotesResult.status === 'rejected' ? ['Market quotes API'] : []),
      ...(quotesResult.status === 'fulfilled' && quotesResult.value.status !== 'SUCCESS' ? ['Market quote quality'] : []),
      ...(quotesResult.status === 'fulfilled' ? quotesResult.value.missingSymbols.map((symbol) => `${symbol} market quote`) : []),
      ...researchResults.flatMap((result, index) =>
        result.status === 'rejected' ? [`${watchlist[index].symbol} research`] : [],
      ),
    ]
    return <ApiTodayPage
      alerts={alertsResult.status === 'fulfilled' ? alertsResult.value.items : []}
      asOf={decisionTime}
      health={healthResult.status === 'fulfilled' ? healthResult.value : null}
      portfolio={portfolioResult.status === 'fulfilled' ? portfolioResult.value : null}
      quotes={quotesResult.status === 'fulfilled' ? quotesResult.value.items : []}
      research={research}
      unavailableDomains={unavailableDomains}
    />
  } catch (error) {
    reportLiveDataFailure('/', 'route', error)
    return <ApiFailurePage currentPath="/" title="Today" />
  }
}
