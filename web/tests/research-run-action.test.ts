import { beforeEach, describe, expect, it, vi } from 'vitest'

import { startResearchRunAction } from '../app/research/actions'
import { initialResearchRunActionState } from '../lib/research-run-action-state'
import { createResearchRun, LiveDataApiError } from '../lib/server/live-data-api'

vi.mock('../lib/server/live-data-api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/server/live-data-api')>()
  return { ...original, createResearchRun: vi.fn() }
})

const createRun = vi.mocked(createResearchRun)

function formData(values: Record<string, string>) {
  const data = new FormData()
  for (const [key, value] of Object.entries(values)) data.set(key, value)
  return data
}

beforeEach(() => {
  vi.clearAllMocks()
  process.env.WEB_DATA_MODE = 'api'
  process.env.API_BASE_URL = 'http://127.0.0.1:8000'
})

describe('research run Server Action', () => {
  it('normalizes the symbol and admits one aware point-in-time run', async () => {
    createRun.mockResolvedValue({
      dataCutoff: '2026-09-07T01:00:00Z',
      decisionTime: '2026-09-07T01:00:00Z',
      runId: '10000000-0000-0000-0000-000000000099',
      runType: 'RESEARCH',
      status: 'QUEUED',
      symbol: 'NVDA',
    })

    const state = await startResearchRunAction(
      initialResearchRunActionState,
      formData({ idempotency_key: 'research-form-1', symbol: ' nvda ' }),
    )

    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        baseUrl: 'http://127.0.0.1:8000/',
        decisionTime: expect.stringMatching(/Z$/),
      }),
      'NVDA',
      'research-form-1',
    )
    expect(state).toEqual({
      message: 'Deterministic research run queued.',
      runId: '10000000-0000-0000-0000-000000000099',
      status: 'success',
      symbol: 'NVDA',
    })
  })

  it('rejects an invalid symbol and missing idempotency key without an API call', async () => {
    await expect(startResearchRunAction(
      initialResearchRunActionState,
      formData({ idempotency_key: 'research-form-1', symbol: 'NVDA!' }),
    )).resolves.toMatchObject({ status: 'error', symbol: 'NVDA!' })
    await expect(startResearchRunAction(
      initialResearchRunActionState,
      formData({ symbol: 'NVDA' }),
    )).resolves.toMatchObject({ status: 'error', symbol: 'NVDA' })
    expect(createRun).not.toHaveBeenCalled()
  })

  it('reports admission saturation without substituting Fixture data', async () => {
    createRun.mockRejectedValue(new LiveDataApiError('response', 'HTTP 429', 429))

    const state = await startResearchRunAction(
      initialResearchRunActionState,
      formData({ idempotency_key: 'research-form-1', symbol: 'NVDA' }),
    )

    expect(state).toEqual({
      message: 'Research capacity is busy. Try again shortly.',
      runId: null,
      status: 'error',
      symbol: 'NVDA',
    })
  })

  it('refuses admission outside API mode', async () => {
    process.env.WEB_DATA_MODE = 'fixture'

    const state = await startResearchRunAction(
      initialResearchRunActionState,
      formData({ idempotency_key: 'research-form-1', symbol: 'NVDA' }),
    )

    expect(state).toMatchObject({ status: 'error', symbol: 'NVDA' })
    expect(createRun).not.toHaveBeenCalled()
  })
})
