import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}))

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
})

function apiMode() {
  vi.stubEnv('WEB_DATA_MODE', 'api')
  vi.stubEnv('API_BASE_URL', 'http://api.test')
}

describe('API mode fixture boundary', () => {
  it('renders an honest empty Alerts state without Fixture facts', async () => {
    apiMode()
    vi.doMock('../lib/server/live-data-api', () => ({ getAlerts: vi.fn(async () => ({ items: [], nextCursor: null })) }))
    const { default: AlertsRoute } = await import('../app/alerts/page')

    render(await AlertsRoute())

    expect(screen.getByRole('status', { name: 'No persisted alerts' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Configure alert monitoring' })).toHaveAttribute('href', '/watchlist')
    expect(screen.getByRole('status', { name: 'No persisted alerts' })).toHaveTextContent('monitoring thresholds')
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('routes persisted Alert records into the usable API Alerts surface', async () => {
    apiMode()
    vi.doMock('../lib/server/live-data-api', () => ({
      getAlerts: vi.fn(async () => ({
        items: [{
          acknowledgedAt: null, acknowledgedBy: null, alertKey: 'NVDA:price-gap', conditions: [],
          correlationId: '10000000-0000-0000-0000-000000000099', createdAt: '2026-08-29T09:21:00Z',
          dataQuality: { coverage: 'IEX' }, eventTime: '2026-08-29T09:20:00Z',
          id: '10000000-0000-0000-0000-000000000001', materiality: '0.075', metrics: { move: '0.081' },
          ruleId: 'price-gap', ruleVersion: 'price-gap-v2', severity: 'HIGH', symbol: 'NVDA',
        }],
        nextCursor: null,
      })),
    }))
    const { default: AlertsRoute } = await import('../app/alerts/page')

    render(await AlertsRoute())

    expect(screen.getByRole('link', { name: 'NVDA research' })).toBeInTheDocument()
    expect(screen.getByText('price-gap · price-gap-v2')).toBeInTheDocument()
    expect(screen.queryByText(/Detailed presentation remains constrained/)).not.toBeInTheDocument()
  })

  it('renders an honest empty Weekly Review state without Fixture facts', async () => {
    apiMode()
    vi.doMock('../lib/server/live-data-api', () => ({ getWeeklyReviews: vi.fn(async () => ({ items: [], nextCursor: null })) }))
    const { default: WeeklyReviewRoute } = await import('../app/weekly-review/page')

    render(await WeeklyReviewRoute())

    expect(screen.getByRole('status', { name: 'No persisted weekly reviews' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review research decisions' })).toHaveAttribute('href', '/research')
    expect(screen.getByRole('status', { name: 'No persisted weekly reviews' })).toHaveTextContent(
      'eligible decision outcomes mature',
    )
    expect(screen.queryByRole('link', { name: 'Review Today' })).not.toBeInTheDocument()
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('loads the latest persisted Weekly Review detail in API mode', async () => {
    apiMode()
    const getWeeklyReviewDetail = vi.fn(async () => ({
      approvals: [], attributions: [], calibration: [], lessons: [], outcomes: [], replays: [],
      review: { dataCutoff: '2026-08-21T20:00:00Z', id: 'r1', status: 'COMPLETED' },
    }))
    vi.doMock('../lib/server/live-data-api', () => ({
      getWeeklyReviewDetail,
      getWeeklyReviews: vi.fn(async () => ({ items: [{ id: 'r1' }], nextCursor: null })),
    }))
    const { default: WeeklyReviewRoute } = await import('../app/weekly-review/page')

    render(await WeeklyReviewRoute())

    expect(getWeeklyReviewDetail).toHaveBeenCalledWith(expect.objectContaining({ decisionTime: expect.any(String) }), 'r1')
    expect(screen.getByRole('heading', { name: 'Weekly Review' })).toBeInTheDocument()
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('renders persisted Run metadata instead of substituting a Fixture trace', async () => {
    apiMode()
    vi.doMock('../lib/server/live-data-api', () => ({
      getResearchRun: vi.fn(async () => ({
        dataCutoff: '2026-08-31T12:00:00Z',
        decisionTime: '2026-08-31T12:00:00Z',
        runId: '10000000-0000-0000-0000-000000000099',
        runType: 'RESEARCH',
        status: 'RUNNING',
        symbol: 'NVDA',
      })),
    }))
    const { default: RunTraceRoute } = await import('../app/runs/[runId]/page')

    render(await RunTraceRoute({ params: Promise.resolve({ runId: '10000000-0000-0000-0000-000000000099' }) }))

    expect(screen.getByText('10000000-0000-0000-0000-000000000099')).toBeInTheDocument()
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('resolves the latest Run Trace alias before loading persisted metadata', async () => {
    apiMode()
    const latest = {
      dataCutoff: '2026-08-31T12:00:00Z',
      decisionTime: '2026-08-31T12:00:00Z',
      runId: '10000000-0000-0000-0000-000000000099',
      runType: 'RESEARCH',
      status: 'RUNNING',
      symbol: 'NVDA',
    }
    const getLatestResearchRun = vi.fn(async () => latest)
    const getResearchRun = vi.fn()
    vi.doMock('../lib/server/live-data-api', () => ({ getLatestResearchRun, getResearchRun }))
    const { default: RunTraceRoute } = await import('../app/runs/[runId]/page')

    render(await RunTraceRoute({ params: Promise.resolve({ runId: 'latest' }) }))

    expect(getLatestResearchRun).toHaveBeenCalledWith(expect.objectContaining({ decisionTime: expect.any(String) }))
    expect(getResearchRun).not.toHaveBeenCalled()
    expect(screen.getByText(latest.runId)).toBeInTheDocument()
  })

  it('does not merge Fixture policy data into API-mode Eval', async () => {
    apiMode()
    vi.doMock('../lib/server/live-data-api', () => ({ getEvalRuns: vi.fn(async () => ({ items: [], nextCursor: null })) }))
    vi.doMock('../lib/server/eval-report', () => ({ loadEvalReport: vi.fn(async () => null) }))
    const { default: EvalRoute } = await import('../app/eval/page')

    render(await EvalRoute())

    expect(screen.getByRole('status', { name: 'No persisted evaluation runs' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'No persisted evaluation runs' })).toHaveTextContent(
      'operator-only offline evaluation persistence workflow',
    )
    expect(screen.queryByRole('link', { name: 'Review Today' })).not.toBeInTheDocument()
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('renders the latest persisted evaluation evidence in API mode', async () => {
    apiMode()
    const run = {
      id: 'eval-1', status: 'PASSED', passed: true, mode: 'fixture', datasetVersion: 'eval-v0.2.0',
      caseCount: 200, dataCutoff: '2026-08-21T20:00:00Z', modelVersion: 'model-v1',
      promptVersion: 'prompt-v1', researchScoringPolicyVersion: 'research-v1', riskPolicyVersion: 'risk-v1',
      executionPolicyVersion: 'execution-v1', confidencePolicyVersion: 'confidence-v1', gatePolicyVersion: 'gates-v1',
      summaryHash: 'a'.repeat(64), createdAt: '2026-08-29T09:20:00Z',
    }
    const getEvalRunDetail = vi.fn(async () => ({
      run, metrics: [{ name: 'directional_accuracy', value: '0.91', caseIds: ['r1'], caseHashes: ['b'.repeat(64)] }],
      gates: [{ name: 'directional_accuracy', comparison: 'AT_LEAST', threshold: '0.8', observed: '0.91', passed: true, reason: 'meets threshold' }],
    }))
    vi.doMock('../lib/server/live-data-api', () => ({
      getEvalRunDetail,
      getEvalRuns: vi.fn(async () => ({ items: [run], nextCursor: null })),
    }))
    const { default: EvalRoute } = await import('../app/eval/page')

    render(await EvalRoute())

    expect(getEvalRunDetail).toHaveBeenCalledWith(expect.objectContaining({ decisionTime: expect.any(String) }), 'eval-1')
    expect(screen.getByRole('heading', { name: 'Persisted evaluation run' })).toBeInTheDocument()
    expect(screen.getAllByText('directional_accuracy')).toHaveLength(2)
    expect(screen.getByText('model-v1')).toBeInTheDocument()
  })
})
