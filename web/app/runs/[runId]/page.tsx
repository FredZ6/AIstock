import { RunTracePage } from '../../../components/trace/run-trace-page'
import { ApiFailurePage, ApiRunMetadataPage } from '../../../components/live/api-pages'
import { MissingFixturePage } from '../../../components/states/missing-fixture-page'
import { readWebDataConfig } from '../../../lib/server/data-mode'
import { reportLiveDataFailure } from '../../../lib/server/live-data-diagnostics'
import { getLatestResearchRun, getResearchRun, getResearchRunReport } from '../../../lib/server/live-data-api'

export default async function RunTraceRoute({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params
  try {
    const config = readWebDataConfig(process.env)
    if (config.mode === 'fixture') {
      const { getFixtureRunTrace } = await import('../../../lib/fixtures')
      const snapshot = getFixtureRunTrace(runId)
      return snapshot
        ? <RunTracePage snapshot={snapshot} />
        : <MissingFixturePage currentPath="/runs/latest" entity={`Run · ${runId}`} returnHref="/" returnLabel="Return to Today" />
    }
    const asOf = new Date().toISOString()
    const options = { baseUrl: config.baseUrl, decisionTime: asOf }
    const run = runId === 'latest'
      ? await getLatestResearchRun(options)
      : await getResearchRun(options, runId)
    const report = run.status === 'COMPLETED' ? await getResearchRunReport(options, run.runId) : undefined
    return <ApiRunMetadataPage report={report} run={run} />
  } catch (error) {
    reportLiveDataFailure(`/runs/${runId}`, 'research-run', error)
    return <ApiFailurePage currentPath={`/runs/${runId}`} title="Run Trace" />
  }
}
