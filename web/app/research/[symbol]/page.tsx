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
    const [quotesResult, recordsResult] = await Promise.allSettled([
      getMarketQuotes(options, [normalized]),
      getStockResearch(options, normalized),
    ])
    if (quotesResult.status === 'rejected' && recordsResult.status === 'rejected') {
      return <ApiFailurePage currentPath={`/research/${normalized}`} title={`${normalized} research`} />
    }
    return <ApiResearchPage
      asOf={asOf}
      quote={quotesResult.status === 'fulfilled' ? quotesResult.value.items[0] ?? null : null}
      records={recordsResult.status === 'fulfilled' ? recordsResult.value : []}
      symbol={normalized}
      unavailableDomains={[
        ...(quotesResult.status === 'rejected' ? ['Market quotes API'] : []),
        ...(quotesResult.status === 'fulfilled' && quotesResult.value.status !== 'SUCCESS' ? ['Market quote quality'] : []),
        ...(recordsResult.status === 'rejected' ? ['Research API'] : []),
      ]}
    />
  } catch {
    return <ApiFailurePage currentPath={`/research/${normalized}`} title={`${normalized} research`} />
  }
}
