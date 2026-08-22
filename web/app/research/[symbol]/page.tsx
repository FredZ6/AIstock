import { ResearchPage } from '../../../components/research/research-page'
import { MissingFixturePage } from '../../../components/states/missing-fixture-page'
import { getFixtureResearchSnapshot } from '../../../lib/fixtures'

export default async function ResearchRoute({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params
  const snapshot = getFixtureResearchSnapshot(symbol)
  return snapshot
    ? <ResearchPage snapshot={snapshot} />
    : <MissingFixturePage currentPath="/research/NVDA" entity={`${symbol.toUpperCase()} research`} returnHref="/watchlist" returnLabel="Return to watchlist" />
}
