import 'server-only'

import type { ApiWatchlistItem } from '../product-types'
import { parseWatchlistRow, parseWatchlistRows } from '../watchlist-contract'

type Fetch = typeof fetch

export type WatchlistClientOptions = {
  baseUrl: string
  fetchImpl?: Fetch
  timeoutMs?: number
}

export type AddWatchlistItem = {
  dailyResearch: boolean
  intradayMonitoring: boolean
  symbol: string
  thresholds: Record<string, string>
}

export type PatchWatchlistItem = {
  dailyResearch?: boolean
  intradayMonitoring?: boolean
  thresholds?: Record<string, string>
}

export type WatchlistApiErrorKind = 'contract' | 'response' | 'unavailable'

export class WatchlistApiError extends Error {
  readonly kind: WatchlistApiErrorKind
  readonly status?: number

  constructor(kind: WatchlistApiErrorKind, message: string, status?: number) {
    super(message)
    this.name = 'WatchlistApiError'
    this.kind = kind
    this.status = status
  }
}

function validSymbol(value: string): string {
  if (!/^[A-Z.]{1,10}$/.test(value)) {
    throw new WatchlistApiError('contract', 'Watchlist symbol is invalid')
  }
  return value
}

async function request(
  { baseUrl, fetchImpl = fetch, timeoutMs = 5_000 }: WatchlistClientOptions,
  path: string,
  init: RequestInit,
): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  let response: Response

  try {
    response = await fetchImpl(new URL(path, baseUrl).toString(), {
      ...init,
      signal: controller.signal,
    })
  } catch {
    throw new WatchlistApiError('unavailable', 'Watchlist API is unavailable')
  } finally {
    clearTimeout(timeout)
  }

  if (!response.ok) {
    throw new WatchlistApiError(
      'response',
      `Watchlist API returned HTTP ${response.status}`,
      response.status,
    )
  }

  return response
}

async function responseItem(response: Response): Promise<ApiWatchlistItem> {
  try {
    return parseWatchlistRow(await response.json())
  } catch {
    throw new WatchlistApiError('contract', 'Watchlist API returned an invalid response')
  }
}

export async function listWatchlist(options: WatchlistClientOptions): Promise<ApiWatchlistItem[]> {
  const response = await request(options, '/api/v1/watchlist', {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
    method: 'GET',
  })
  try {
    return parseWatchlistRows(await response.json())
  } catch {
    throw new WatchlistApiError('contract', 'Watchlist API returned an invalid response')
  }
}

export async function addWatchlistItem(
  options: WatchlistClientOptions,
  item: AddWatchlistItem,
): Promise<ApiWatchlistItem> {
  validSymbol(item.symbol)
  const response = await request(options, '/api/v1/watchlist', {
    body: JSON.stringify({
      symbol: item.symbol,
      daily_research: item.dailyResearch,
      intraday_monitoring: item.intradayMonitoring,
      thresholds: item.thresholds,
    }),
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    method: 'POST',
  })
  return responseItem(response)
}

export async function patchWatchlistItem(
  options: WatchlistClientOptions,
  symbol: string,
  patch: PatchWatchlistItem,
): Promise<ApiWatchlistItem> {
  validSymbol(symbol)
  const payload: Record<string, unknown> = {}
  if (patch.dailyResearch !== undefined) payload.daily_research = patch.dailyResearch
  if (patch.intradayMonitoring !== undefined) {
    payload.intraday_monitoring = patch.intradayMonitoring
  }
  if (patch.thresholds !== undefined) payload.thresholds = patch.thresholds
  const response = await request(options, `/api/v1/watchlist/${encodeURIComponent(symbol)}`, {
    body: JSON.stringify(payload),
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    method: 'PATCH',
  })
  return responseItem(response)
}

export async function deleteWatchlistItem(
  options: WatchlistClientOptions,
  symbol: string,
): Promise<void> {
  validSymbol(symbol)
  const response = await request(options, `/api/v1/watchlist/${encodeURIComponent(symbol)}`, {
    headers: { Accept: 'application/json' },
    method: 'DELETE',
  })
  if (response.status !== 204) {
    throw new WatchlistApiError(
      'contract',
      'Watchlist API returned an invalid delete response',
      response.status,
    )
  }
}
