import { ApiFailurePage, ApiTodayPage } from '../components/live/api-pages'
import { TodayPage } from '../components/today-page'
import { readWebDataConfig } from '../lib/server/data-mode'
import { reportLiveDataFailure } from '../lib/server/live-data-diagnostics'
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
    const [watchlistResult, healthResult, portfolioResult] = await Promise.allSettled([
      listWatchlist({ baseUrl: config.baseUrl }),
      getProviderHealth(options),
      getPortfolioSummary(options),
    ])
    if (watchlistResult.status === 'rejected') reportLiveDataFailure('/', 'watchlist', watchlistResult.reason)
    if (healthResult.status === 'rejected') reportLiveDataFailure('/', 'provider-health', healthResult.reason)
    if (portfolioResult.status === 'rejected') reportLiveDataFailure('/', 'portfolio', portfolioResult.reason)
    const watchlist = watchlistResult.status === 'fulfilled' ? watchlistResult.value : []
    const quotesResult = watchlist.length
      ? await getMarketQuotes(options, watchlist.map((item) => item.symbol)).then(
        (value) => ({ status: 'fulfilled' as const, value }),
        (error) => {
          reportLiveDataFailure('/', 'market-quotes', error)
          return { status: 'rejected' as const }
        },
      )
      : { status: 'rejected' as const }
    const availableFacts = [healthResult, portfolioResult, quotesResult]
      .some((result) => result.status === 'fulfilled')
    if (!availableFacts) return <ApiFailurePage currentPath="/" title="Today" />
    const unavailableDomains = [
      ...(watchlistResult.status === 'rejected' ? ['Watchlist API'] : []),
      ...(healthResult.status === 'rejected' ? ['Provider health'] : []),
      ...(portfolioResult.status === 'rejected' ? ['Portfolio API'] : []),
      ...(quotesResult.status === 'rejected' ? ['Market quotes API'] : []),
      ...(quotesResult.status === 'fulfilled' && quotesResult.value.status !== 'SUCCESS' ? ['Market quote quality'] : []),
      ...(quotesResult.status === 'fulfilled' ? quotesResult.value.missingSymbols.map((symbol) => `${symbol} market quote`) : []),
    ]
    return <ApiTodayPage
      asOf={decisionTime}
      health={healthResult.status === 'fulfilled' ? healthResult.value : null}
      portfolio={portfolioResult.status === 'fulfilled' ? portfolioResult.value : null}
      quotes={quotesResult.status === 'fulfilled' ? quotesResult.value.items : []}
      unavailableDomains={unavailableDomains}
    />
  } catch (error) {
    reportLiveDataFailure('/', 'route', error)
    return <ApiFailurePage currentPath="/" title="Today" />
  }
}
