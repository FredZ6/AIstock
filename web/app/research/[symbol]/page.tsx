import { ApiFailurePage, ApiResearchPage } from '../../../components/live/api-pages'
import { ResearchPage } from '../../../components/research/research-page'
import { MissingFixturePage } from '../../../components/states/missing-fixture-page'
import { readWebDataConfig } from '../../../lib/server/data-mode'
import { getMarketQuotes, getStockResearch } from '../../../lib/server/live-data-api'

export default async function ResearchRoute({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params
  const normalized = symbol.toUpperCase()
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { getFixtureResearchSnapshot } = await import('../../../lib/fixtures')
      const snapshot = getFixtureResearchSnapshot(normalized)
      return snapshot
        ? <ResearchPage snapshot={snapshot} />
        : <MissingFixturePage currentPath="/research/NVDA" entity={`${normalized} research`} returnHref="/watchlist" returnLabel="Return to watchlist" />
    }
    const asOf = new Date().toISOString()
    const options = { baseUrl: config.baseUrl, decisionTime: asOf }
    const [quotes, records] = await Promise.all([
      getMarketQuotes(options, [normalized]),
      getStockResearch(options, normalized),
    ])
    return <ApiResearchPage asOf={asOf} quote={quotes.items[0] ?? null} records={records} symbol={normalized} />
  } catch {
    return <ApiFailurePage currentPath={`/research/${normalized}`} title={`${normalized} research`} />
  }
}
