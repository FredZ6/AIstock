import { EvalAdminPage } from '../../components/eval/eval-admin-page'
import { ApiCollectionPage, ApiFailurePage } from '../../components/live/api-pages'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { loadEvalReport } from '../../lib/server/eval-report'
import { getEvalRuns } from '../../lib/server/live-data-api'

export const dynamic = 'force-dynamic'

export default async function EvalRoute() {
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { fixtureEvalAdminSnapshot } = await import('../../lib/fixtures')
      const evaluation = await loadEvalReport()
      return <EvalAdminPage snapshot={{ ...fixtureEvalAdminSnapshot, evaluation }} />
    }
    const asOf = new Date().toISOString()
    const page = await getEvalRuns({ baseUrl: config.baseUrl, decisionTime: asOf })
    return <ApiCollectionPage asOf={asOf} count={page.items.length} currentPath="/eval" emptyTitle="No persisted evaluation runs" title="Eval & Admin" />
  } catch (error) {
    reportLiveDataFailure('/eval', 'eval-runs', error)
    return <ApiFailurePage currentPath="/eval" title="Eval & Admin" />
  }
}
