import { EvalAdminPage } from '../../components/eval/eval-admin-page'
import { ApiCollectionPage, ApiEvalPage, ApiFailurePage } from '../../components/live/api-pages'
import { readWebDataConfig } from '../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../lib/server/live-data-diagnostics'
import { loadEvalReport } from '../../lib/server/eval-report'
import { getEvalRunDetail, getEvalRuns } from '../../lib/server/live-data-api'

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
    if (page.items.length === 0) return <ApiCollectionPage
      asOf={asOf}
      count={0}
      currentPath="/eval"
      emptyMessage="Persisted evaluation evidence requires the operator-only offline evaluation persistence workflow. No browser producer or automatic policy activation is available."
      emptyTitle="No persisted evaluation runs"
      title="Eval & Admin"
    />
    const detail = await getEvalRunDetail({ baseUrl: config.baseUrl, decisionTime: asOf }, page.items[0].id)
    return <ApiEvalPage asOf={asOf} detail={detail} />
  } catch (error) {
    reportLiveDataFailure('/eval', 'eval-runs', error)
    return <ApiFailurePage currentPath="/eval" title="Eval & Admin" />
  }
}
