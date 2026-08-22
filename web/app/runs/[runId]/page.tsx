import { RunTracePage } from '../../../components/trace/run-trace-page'
import { MissingFixturePage } from '../../../components/states/missing-fixture-page'
import { getFixtureRunTrace } from '../../../lib/fixtures'

export default async function RunTraceRoute({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params
  const snapshot = getFixtureRunTrace(runId)
  return snapshot
    ? <RunTracePage snapshot={snapshot} />
    : <MissingFixturePage currentPath="/runs/latest" entity={`Run · ${runId}`} returnHref="/" returnLabel="Return to Today" />
}
