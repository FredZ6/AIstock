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
import { availabilityFromDomain, type AvailabilityFact } from '../lib/availability'

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
    const fact = (input: Parameters<typeof availabilityFromDomain>[0]): AvailabilityFact => availabilityFromDomain(input)
    const availabilityFacts = [
      ...(watchlistResult.status === 'rejected' ? [fact({ key: 'api:watchlist', label: 'Watchlist API', reason: 'The Watchlist API request failed.', state: 'FAILURE', action: { href: '/watchlist', label: 'Review watchlist' } })] : []),
      ...(healthResult.status === 'rejected' ? [fact({ key: 'provider:health', label: 'Provider health', reason: 'The provider health API request failed.', state: 'FAILURE', action: { href: '/eval', label: 'Review runtime' } })] : []),
      ...(portfolioResult.status === 'rejected' ? [fact({ key: 'api:portfolio', label: 'Portfolio API', reason: 'The Paper Portfolio API request failed.', state: 'FAILURE', action: { href: '/portfolio', label: 'Review portfolio' } })] : []),
      ...(alertsResult.status === 'rejected' ? [fact({ key: 'api:alerts', label: 'Alerts API', reason: 'The Alerts API request failed.', state: 'FAILURE', action: { href: '/alerts', label: 'Review alerts' } })] : []),
      ...(quotesResult.status === 'rejected' ? [fact({ key: 'market:api', label: 'Market quotes API', reason: 'The market quote API request failed.', state: 'FAILURE', action: { href: '/watchlist', label: 'Review market data' } })] : []),
      ...(quotesResult.status === 'fulfilled' && quotesResult.value.status !== 'SUCCESS' ? [fact({ key: 'market:quality', label: 'Market quote quality', reason: 'Persisted market quote coverage or quality is degraded.', state: 'DEGRADED', action: { href: '/watchlist', label: 'Review quote quality' } })] : []),
      ...(quotesResult.status === 'fulfilled' ? quotesResult.value.missingSymbols.map((symbol) => fact({ key: `market:quote:${symbol}`, label: `${symbol} market quote`, reason: 'No point-in-time eligible market quote was persisted.', state: 'EMPTY', action: { href: '/watchlist', label: 'Review market ingestion' } })) : []),
      ...researchResults.flatMap((result, index) => {
        const symbol = watchlist[index].symbol
        if (result.status === 'rejected') return [fact({ key: `research:${symbol}`, label: `${symbol} research`, reason: 'The persisted research API request failed.', state: 'FAILURE', action: { href: `/research/${symbol}`, label: `Review ${symbol} research` } })]
        return (result.value.unavailableDomains ?? []).map((domain) => fact({
          key: `research:${symbol}:${domain}`,
          label: `${symbol} ${domain.replaceAll('_', ' ').toLowerCase()}`,
          reason: result.value.unavailableReasons?.[domain] ?? `No persisted ${domain.toLowerCase()} fact is available and no producer reported a reason.`,
          action: /unsupported|no approved/i.test(result.value.unavailableReasons?.[domain] ?? '')
            ? null
            : { href: `/research/${symbol}`, label: `Review ${symbol} research` },
        }))
      }),
    ]
    return <ApiTodayPage
      alerts={alertsResult.status === 'fulfilled' ? alertsResult.value.items : []}
      asOf={decisionTime}
      health={healthResult.status === 'fulfilled' ? healthResult.value : null}
      portfolio={portfolioResult.status === 'fulfilled' ? portfolioResult.value : null}
      quotes={quotesResult.status === 'fulfilled' ? quotesResult.value.items : []}
      research={research}
      availabilityFacts={availabilityFacts}
    />
  } catch (error) {
    reportLiveDataFailure('/', 'route', error)
    return <ApiFailurePage currentPath="/" title="Today" />
  }
}
