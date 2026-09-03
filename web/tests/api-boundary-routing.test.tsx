import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('renders an honest empty Weekly Review state without Fixture facts', async () => {
    apiMode()
    vi.doMock('../lib/server/live-data-api', () => ({ getWeeklyReviews: vi.fn(async () => ({ items: [], nextCursor: null })) }))
    const { default: WeeklyReviewRoute } = await import('../app/weekly-review/page')

    render(await WeeklyReviewRoute())

    expect(screen.getByRole('status', { name: 'No persisted weekly reviews' })).toBeInTheDocument()
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
        status: 'COMPLETED',
        symbol: 'NVDA',
      })),
    }))
    const { default: RunTraceRoute } = await import('../app/runs/[runId]/page')

    render(await RunTraceRoute({ params: Promise.resolve({ runId: '10000000-0000-0000-0000-000000000099' }) }))

    expect(screen.getByText('10000000-0000-0000-0000-000000000099')).toBeInTheDocument()
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })

  it('does not merge Fixture policy data into API-mode Eval', async () => {
    apiMode()
    vi.doMock('../lib/server/live-data-api', () => ({ getEvalRuns: vi.fn(async () => ({ items: [], nextCursor: null })) }))
    vi.doMock('../lib/server/eval-report', () => ({ loadEvalReport: vi.fn(async () => null) }))
    const { default: EvalRoute } = await import('../app/eval/page')

    render(await EvalRoute())

    expect(screen.getByRole('status', { name: 'No persisted evaluation runs' })).toBeInTheDocument()
    expect(screen.queryByText(/fixture mode|frozen synthetic/i)).not.toBeInTheDocument()
  })
})
