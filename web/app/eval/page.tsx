import { EvalAdminPage } from '../../components/eval/eval-admin-page'
import { fixtureEvalAdminSnapshot } from '../../lib/fixtures'
import { loadEvalReport } from '../../lib/server/eval-report'

export const dynamic = 'force-dynamic'

export default async function EvalRoute() {
  const evaluation = await loadEvalReport()
  return <EvalAdminPage snapshot={{ ...fixtureEvalAdminSnapshot, evaluation }} />
}
