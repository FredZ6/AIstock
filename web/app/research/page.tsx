import { ApiFailurePage } from '../../components/live/api-pages'
import { ResearchDirectoryPage, type ResearchDirectorySymbol } from '../../components/research/research-directory-page'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { getStockResearch } from '../../lib/server/live-data-api'
import { listWatchlist } from '../../lib/server/watchlist-api'

export const dynamic = 'force-dynamic'

export default async function ResearchDirectoryRoute() {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { fixtureWatchlistSnapshot } = await import('../../lib/fixtures')
      return <ResearchDirectoryPage mode="fixture" symbols={fixtureWatchlistSnapshot.symbols.map((item) => ({
        lastResearchAt: item.lastResearchAt,
        opinion: item.researchOpinion,
        symbol: item.symbol,
      }))} />
    }

    const items = await listWatchlist({ baseUrl: config.baseUrl })
    const decisionTime = new Date().toISOString()
    const results = await Promise.all(items.map(async (item) => {
      try {
        const research = await getStockResearch({ baseUrl: config.baseUrl, decisionTime }, item.symbol)
        const latest = [...research.records].sort((left, right) => right.asOf.localeCompare(left.asOf))[0]
        return { symbol: { lastResearchAt: latest?.asOf ?? null, opinion: latest?.opinion ?? null, symbol: item.symbol }, unavailable: false }
      } catch (error) {
        reportLiveDataFailure('/research', `${item.symbol}-research`, error)
        return { symbol: { lastResearchAt: null, opinion: null, symbol: item.symbol }, unavailable: true }
      }
    }))
    const symbols: ResearchDirectorySymbol[] = results.map((result) => result.symbol)
    return <ResearchDirectoryPage
      mode="api"
      symbols={symbols}
      unavailableSymbols={results.filter((result) => result.unavailable).map((result) => result.symbol.symbol)}
    />
  } catch (error) {
    reportLiveDataFailure('/research', 'research-directory', error)
    return <ApiFailurePage currentPath="/research" title="Stock research" />
  }
}
