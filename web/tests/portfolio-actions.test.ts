import { beforeEach, describe, expect, it, vi } from 'vitest'

import { initializePortfolioAction } from '../app/portfolio/actions'
import { initializePortfolio } from '../lib/server/live-data-api'
import { revalidatePath } from 'next/cache'

vi.mock('../lib/server/live-data-api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/server/live-data-api')>()
  return { ...original, initializePortfolio: vi.fn() }
})
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

beforeEach(() => {
  vi.clearAllMocks()
  process.env.WEB_DATA_MODE = 'api'
  process.env.API_BASE_URL = 'http://127.0.0.1:8000'
})

describe('paper portfolio initialization action', () => {
  it('uses one stable form-scoped request identity and revalidates after persistence', async () => {
    vi.mocked(initializePortfolio).mockResolvedValue({} as never)

    const form = new FormData()
    form.set('effective_at', '2026-09-02T01:00:00Z')
    form.set('idempotency_key', 'portfolio-init:2026-09-02T01:00:00Z')
    await initializePortfolioAction(form)

    expect(initializePortfolio).toHaveBeenCalledWith(
      expect.objectContaining({
        baseUrl: 'http://127.0.0.1:8000/',
        decisionTime: '2026-09-02T01:00:00Z',
      }),
      'portfolio-init:2026-09-02T01:00:00Z',
    )
    expect(vi.mocked(revalidatePath)).toHaveBeenCalledWith('/portfolio')
  })

  it('does not revalidate when persistence fails', async () => {
    vi.mocked(initializePortfolio).mockRejectedValue(new Error('backend unavailable'))

    const form = new FormData()
    form.set('effective_at', '2026-09-02T01:00:00Z')
    form.set('idempotency_key', 'portfolio-init:2026-09-02T01:00:00Z')
    await expect(initializePortfolioAction(form)).rejects.toThrow('Paper portfolio initialization failed')
    expect(vi.mocked(revalidatePath)).not.toHaveBeenCalled()
  })
})
