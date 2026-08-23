import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  addWatchlistAction,
  deleteWatchlistAction,
  updateWatchlistAction,
} from '../app/watchlist/actions'
import { initialWatchlistActionState } from '../lib/watchlist-action-state'
import {
  addWatchlistItem,
  deleteWatchlistItem,
  patchWatchlistItem,
  WatchlistApiError,
} from '../lib/server/watchlist-api'
import { revalidatePath } from 'next/cache'

vi.mock('../lib/server/watchlist-api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/server/watchlist-api')>()
  return {
    ...original,
    addWatchlistItem: vi.fn(),
    deleteWatchlistItem: vi.fn(),
    patchWatchlistItem: vi.fn(),
  }
})

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

const addItem = vi.mocked(addWatchlistItem)
const deleteItem = vi.mocked(deleteWatchlistItem)
const patchItem = vi.mocked(patchWatchlistItem)
const revalidate = vi.mocked(revalidatePath)

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

describe('watchlist Server Actions', () => {
  it('rejects invalid add input without calling FastAPI', async () => {
    const state = await addWatchlistAction(
      initialWatchlistActionState,
      formData({ symbol: 'nvda!' }),
    )

    expect(state).toEqual({
      message: 'Symbol must match [A-Z.]{1,10}',
      status: 'error',
      symbol: 'NVDA!',
    })
    expect(addItem).not.toHaveBeenCalled()
    expect(revalidate).not.toHaveBeenCalled()
  })

  it('adds normalized configuration and revalidates only after success', async () => {
    addItem.mockResolvedValue({} as never)

    const state = await addWatchlistAction(
      initialWatchlistActionState,
      formData({ daily_research: 'on', symbol: 'nvda' }),
    )

    expect(addItem).toHaveBeenCalledWith(
      expect.objectContaining({ baseUrl: 'http://127.0.0.1:8000/' }),
      {
        dailyResearch: true,
        intradayMonitoring: false,
        symbol: 'NVDA',
        thresholds: {},
      },
    )
    expect(revalidate).toHaveBeenCalledWith('/watchlist')
    expect(state).toEqual({ message: 'NVDA added.', status: 'success', symbol: 'NVDA' })
  })

  it('updates explicit checkbox values and preserves a Decimal threshold string', async () => {
    patchItem.mockResolvedValue({} as never)

    const state = await updateWatchlistAction(
      'NVDA',
      initialWatchlistActionState,
      formData({ alert_threshold: '0.03', intraday_monitoring: 'on' }),
    )

    expect(patchItem).toHaveBeenCalledWith(
      expect.objectContaining({ baseUrl: 'http://127.0.0.1:8000/' }),
      'NVDA',
      {
        dailyResearch: false,
        intradayMonitoring: true,
        thresholds: { return_5m: '0.03' },
      },
    )
    expect(revalidate).toHaveBeenCalledWith('/watchlist')
    expect(state.status).toBe('success')
  })

  it('rejects an invalid threshold without writing or revalidating', async () => {
    const state = await updateWatchlistAction(
      'NVDA',
      initialWatchlistActionState,
      formData({ alert_threshold: 'two percent' }),
    )

    expect(state).toMatchObject({ status: 'error', symbol: 'NVDA' })
    expect(patchItem).not.toHaveBeenCalled()
    expect(revalidate).not.toHaveBeenCalled()
  })

  it('clears an optional threshold without fabricating a Decimal value', async () => {
    patchItem.mockResolvedValue({} as never)

    const state = await updateWatchlistAction(
      'NVDA',
      initialWatchlistActionState,
      formData({ alert_threshold: '' }),
    )

    expect(patchItem).toHaveBeenCalledWith(
      expect.anything(),
      'NVDA',
      expect.objectContaining({ thresholds: {} }),
    )
    expect(state.status).toBe('success')
  })

  it('deletes through FastAPI and revalidates after confirmation', async () => {
    deleteItem.mockResolvedValue(undefined)

    const state = await deleteWatchlistAction(
      'NVDA',
      initialWatchlistActionState,
      new FormData(),
    )

    expect(deleteItem).toHaveBeenCalledWith(
      expect.objectContaining({ baseUrl: 'http://127.0.0.1:8000/' }),
      'NVDA',
    )
    expect(revalidate).toHaveBeenCalledWith('/watchlist')
    expect(state.status).toBe('success')
  })

  it('returns a safe error and retains the symbol when FastAPI fails', async () => {
    addItem.mockRejectedValue(
      new WatchlistApiError('response', 'Watchlist API returned HTTP 503', 503),
    )

    const state = await addWatchlistAction(
      initialWatchlistActionState,
      formData({ symbol: 'NVDA' }),
    )

    expect(state).toEqual({
      message: 'Unable to persist watchlist changes. Try again.',
      status: 'error',
      symbol: 'NVDA',
    })
    expect(revalidate).not.toHaveBeenCalled()
  })

  it('refuses writes outside explicit API mode', async () => {
    process.env.WEB_DATA_MODE = 'fixture'

    const state = await addWatchlistAction(
      initialWatchlistActionState,
      formData({ symbol: 'NVDA' }),
    )

    expect(state).toMatchObject({ status: 'error', symbol: 'NVDA' })
    expect(addItem).not.toHaveBeenCalled()
    expect(revalidate).not.toHaveBeenCalled()
  })
})
