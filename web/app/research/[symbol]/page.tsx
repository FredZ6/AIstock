import { ApiFailurePage, ApiResearchPage } from '../../../components/live/api-pages'
import { ResearchPage } from '../../../components/research/research-page'
import { MissingFixturePage } from '../../../components/states/missing-fixture-page'
import { readWebDataConfig } from '../../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../../lib/server/live-data-diagnostics'
import { getDataQuality, getMarketQuotes, getStockResearch } from '../../../lib/server/live-data-api'

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
    const [quotesResult, recordsResult, filingQualityResult, factsQualityResult] = await Promise.allSettled([
      getMarketQuotes(options, [normalized]),
      getStockResearch(options, normalized),
      getDataQuality(options, 'SEC', 'filings'),
      getDataQuality(options, 'SEC', 'company_facts'),
    ])
    if (quotesResult.status === 'rejected') reportLiveDataFailure(`/research/${normalized}`, 'market-quotes', quotesResult.reason)
    if (recordsResult.status === 'rejected') reportLiveDataFailure(`/research/${normalized}`, 'research', recordsResult.reason)
    if (filingQualityResult.status === 'rejected') reportLiveDataFailure(`/research/${normalized}`, 'sec-filing-quality', filingQualityResult.reason)
    if (factsQualityResult.status === 'rejected') reportLiveDataFailure(`/research/${normalized}`, 'sec-facts-quality', factsQualityResult.reason)
    if (quotesResult.status === 'rejected' && recordsResult.status === 'rejected') {
      return <ApiFailurePage currentPath={`/research/${normalized}`} title={`${normalized} research`} />
    }
    const filingQuality = filingQualityResult.status === 'fulfilled' ? filingQualityResult.value : []
    const factsQuality = factsQualityResult.status === 'fulfilled' ? factsQualityResult.value : []
    return <ApiResearchPage
      asOf={asOf}
      dataQuality={[
        ...filingQuality,
        ...factsQuality,
      ]}
      financialFacts={recordsResult.status === 'fulfilled' ? recordsResult.value.financialFacts : []}
      quote={quotesResult.status === 'fulfilled' ? quotesResult.value.items[0] ?? null : null}
      records={recordsResult.status === 'fulfilled' ? recordsResult.value.records : []}
      secFilings={recordsResult.status === 'fulfilled' ? recordsResult.value.secFilings : []}
      symbol={normalized}
      unavailableDomains={[
        ...(quotesResult.status === 'rejected' ? ['Market quotes API'] : []),
        ...(quotesResult.status === 'fulfilled' && quotesResult.value.status !== 'SUCCESS' ? ['Market quote quality'] : []),
        ...(recordsResult.status === 'rejected' ? ['Research API'] : []),
        ...(filingQualityResult.status === 'rejected' ? ['SEC filing quality API'] : []),
        ...(factsQualityResult.status === 'rejected' ? ['SEC facts quality API'] : []),
        ...(filingQualityResult.status === 'fulfilled' && (filingQuality.length === 0 || filingQuality.some((item) => item.status !== 'PASS')) ? ['SEC filing quality'] : []),
        ...(factsQualityResult.status === 'fulfilled' && (factsQuality.length === 0 || factsQuality.some((item) => item.status !== 'PASS')) ? ['SEC facts quality'] : []),
      ]}
    />
  } catch (error) {
    reportLiveDataFailure(`/research/${normalized}`, 'route', error)
    return <ApiFailurePage currentPath={`/research/${normalized}`} title={`${normalized} research`} />
  }
}
