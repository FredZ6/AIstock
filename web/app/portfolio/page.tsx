import { ApiFailurePage, ApiPortfolioPage } from '../../components/live/api-pages'
import { PortfolioPage } from '../../components/portfolio/portfolio-page'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { getPortfolioSummary } from '../../lib/server/live-data-api'

export const dynamic = 'force-dynamic'

export default async function PortfolioRoute() {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { fixturePortfolioSnapshot } = await import('../../lib/fixtures')
      return <PortfolioPage snapshot={fixturePortfolioSnapshot} />
    }
    const asOf = new Date().toISOString()
    const portfolio = await getPortfolioSummary({ baseUrl: config.baseUrl, decisionTime: asOf })
    return <ApiPortfolioPage asOf={asOf} portfolio={portfolio} />
  } catch (error) {
    reportLiveDataFailure('/portfolio', 'portfolio', error)
    return <ApiFailurePage currentPath="/portfolio" title="AI Portfolio" />
  }
}
