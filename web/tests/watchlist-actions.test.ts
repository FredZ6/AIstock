import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  addWatchlistAction,
  deleteWatchlistAction,
  refreshWatchlistAction,
  updateWatchlistAction,
} from '../app/watchlist/actions'
import { initialWatchlistActionState } from '../lib/watchlist-action-state'
import {
  addWatchlistItem,
  deleteWatchlistItem,
  listWatchlist,
  patchWatchlistItem,
  refreshWatchlistMarketData,
  WatchlistApiError,
} from '../lib/server/watchlist-api'
import { revalidatePath } from 'next/cache'

vi.mock('../lib/server/watchlist-api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/server/watchlist-api')>()
  return {
    ...original,
    addWatchlistItem: vi.fn(),
    deleteWatchlistItem: vi.fn(),
    listWatchlist: vi.fn(),
    patchWatchlistItem: vi.fn(),
    refreshWatchlistMarketData: vi.fn(),
  }
})

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

const addItem = vi.mocked(addWatchlistItem)
const deleteItem = vi.mocked(deleteWatchlistItem)
const listItems = vi.mocked(listWatchlist)
const patchItem = vi.mocked(patchWatchlistItem)
const refreshData = vi.mocked(refreshWatchlistMarketData)
const revalidate = vi.mocked(revalidatePath)

function formData(values: Record<string, string>) {
  const data = new FormData()
  for (const [key, value] of Object.entries(values)) data.set(key, value)
  return data
}

beforeEach(() => {
  vi.clearAllMocks()
  listItems.mockResolvedValue([])
  process.env.WEB_DATA_MODE = 'api'
  process.env.API_BASE_URL = 'http://127.0.0.1:8000'
  delete process.env.ADMIN_API_TOKEN
})

describe('manual Watchlist market refresh', () => {
  const accepted = {
    dataCutoff: '2026-10-02T20:00:00Z', feed: 'IEX' as const,
    jobIds: ['11111111-1111-4111-8111-111111111111'], message: 'queued',
    requestedAt: '2026-10-05T08:00:00Z', status: 'queued' as const,
    symbolCount: 12, timeframe: '1Day' as const,
  }

  it('sends only the server token in API mode and reports admission truthfully', async () => {
    process.env.ADMIN_API_TOKEN = 'private-token'
    refreshData.mockResolvedValue(accepted)
    const result = await refreshWatchlistAction(initialWatchlistActionState, new FormData())
    expect(refreshData).toHaveBeenCalledOnce()
    expect(refreshData).toHaveBeenCalledWith({ baseUrl: 'http://127.0.0.1:8000/', adminToken: 'private-token' })
    expect(result).toEqual({ message: 'Refresh queued for 12 symbols.', status: 'success' })
    expect(revalidate).toHaveBeenCalledWith('/watchlist')
  })

  it('reports an already processing request without implying prices changed', async () => {
    process.env.ADMIN_API_TOKEN = 'private-token'
    refreshData.mockResolvedValue({ ...accepted, status: 'already_queued' })
    const result = await refreshWatchlistAction(initialWatchlistActionState, new FormData())
    expect(result).toEqual({ message: 'A refresh is already processing for 12 symbols.', status: 'success' })
    expect(revalidate).toHaveBeenCalledWith('/watchlist')
  })

  it('uses singular wording when one symbol is queued', async () => {
    process.env.ADMIN_API_TOKEN = 'private-token'
    refreshData.mockResolvedValue({ ...accepted, symbolCount: 1 })
    expect(await refreshWatchlistAction(initialWatchlistActionState, new FormData()))
      .toEqual({ message: 'Refresh queued for 1 symbol.', status: 'success' })
  })

  it('reports empty and unavailable states without revalidation', async () => {
    process.env.ADMIN_API_TOKEN = 'private-token'
    refreshData.mockResolvedValueOnce({ ...accepted, status: 'no_symbols', symbolCount: 0, jobIds: [], dataCutoff: null, timeframe: null })
    expect(await refreshWatchlistAction(initialWatchlistActionState, new FormData()))
      .toEqual({ message: 'No monitored Watchlist symbols are available to refresh.', status: 'success' })
    refreshData.mockResolvedValueOnce({ ...accepted, status: 'unavailable', jobIds: [] })
    expect(await refreshWatchlistAction(initialWatchlistActionState, new FormData()))
      .toEqual({ message: 'Market data refresh is unavailable. Try again later.', status: 'error' })
    expect(revalidate).not.toHaveBeenCalled()
  })

  it('rejects missing server configuration before any request', async () => {
    const result = await refreshWatchlistAction(initialWatchlistActionState, new FormData())
    expect(result).toEqual({ message: 'Market data refresh is not configured. Contact the operator.', status: 'error' })
    expect(refreshData).not.toHaveBeenCalled()
    expect(revalidate).not.toHaveBeenCalled()
  })

  it('refuses Fixture mode even when a token is configured', async () => {
    process.env.WEB_DATA_MODE = 'fixture'
    process.env.ADMIN_API_TOKEN = 'private-token'
    expect(await refreshWatchlistAction(initialWatchlistActionState, new FormData()))
      .toEqual({ message: 'Market data refresh requires API mode.', status: 'error' })
    expect(refreshData).not.toHaveBeenCalled()
  })

  it('returns actionable limit copy for 409 and sanitizes other failures', async () => {
    process.env.ADMIN_API_TOKEN = 'private-token'
    refreshData.mockRejectedValueOnce(new WatchlistApiError('response', 'secret provider body', 409))
    expect(await refreshWatchlistAction(initialWatchlistActionState, new FormData()))
      .toEqual({ message: 'More than 50 monitored symbols. Reduce the Watchlist and try again.', status: 'error' })
    refreshData.mockRejectedValueOnce(new Error('private-token secret provider body'))
    expect(await refreshWatchlistAction(initialWatchlistActionState, new FormData()))
      .toEqual({ message: 'Unable to request market data refresh. Try again.', status: 'error' })
    expect(revalidate).not.toHaveBeenCalled()
  })
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

  it('rejects an existing symbol without resetting its persisted configuration', async () => {
    listItems.mockResolvedValue([{ symbol: 'NVDA' }] as never)

    const state = await addWatchlistAction(
      initialWatchlistActionState,
      formData({ symbol: 'nvda' }),
    )

    expect(state).toEqual({
      message: 'NVDA is already in the watchlist.',
      status: 'error',
      symbol: 'NVDA',
    })
    expect(addItem).not.toHaveBeenCalled()
    expect(revalidate).not.toHaveBeenCalled()
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
