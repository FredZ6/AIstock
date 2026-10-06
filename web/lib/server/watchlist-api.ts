import 'server-only'

import type { ApiWatchlistItem } from '../product-types'
import { parseAwareInstant } from '../time'
import { parseWatchlistRow, parseWatchlistRows } from '../watchlist-contract'

type Fetch = typeof fetch

export type WatchlistClientOptions = {
  adminToken?: string
  baseUrl: string
  fetchImpl?: Fetch
  timeoutMs?: number
}

export type WatchlistRefreshResult = {
  dataCutoff: string | null
  feed: 'IEX' | null
  jobIds: string[]
  message: string
  requestedAt: string
  status: 'queued' | 'already_queued' | 'no_symbols' | 'unavailable'
  symbolCount: number
  timeframe: '1Min' | '1Day' | null
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
type KnownWatchlistErrorCode = 'PAPER_MODE_REQUIRED' | 'WATCHLIST_REFRESH_LIMIT_EXCEEDED'

export class WatchlistApiError extends Error {
  readonly kind: WatchlistApiErrorKind
  readonly status?: number
  readonly code?: KnownWatchlistErrorCode

  constructor(kind: WatchlistApiErrorKind, message: string, status?: number, code?: KnownWatchlistErrorCode) {
    super(message)
    this.name = 'WatchlistApiError'
    this.kind = kind
    this.status = status
    this.code = code
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
    let code: KnownWatchlistErrorCode | undefined
    if (response.status === 409) {
      try {
        const body: unknown = await response.json()
        const candidate = typeof body === 'object' && body !== null && 'error' in body
          ? body.error : undefined
        const rawCode = typeof candidate === 'object' && candidate !== null && 'code' in candidate
          ? candidate.code : undefined
        if (rawCode === 'PAPER_MODE_REQUIRED' || rawCode === 'WATCHLIST_REFRESH_LIMIT_EXCEEDED') {
          code = rawCode
        }
      } catch {
        // Unknown upstream errors retain only their HTTP status.
      }
    }
    throw new WatchlistApiError(
      'response',
      `Watchlist API returned HTTP ${response.status}`,
      response.status,
      code,
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

const refreshResponseKeys = [
  'data_cutoff', 'feed', 'job_ids', 'message', 'requested_at', 'status',
  'symbol_count', 'timeframe',
] as const
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function parseRefreshResponse(value: unknown): WatchlistRefreshResult {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new TypeError('Refresh response must be an object')
  }
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).length !== refreshResponseKeys.length
    || refreshResponseKeys.some((key) => !Object.hasOwn(row, key))
  ) {
    throw new TypeError('Refresh response fields are invalid')
  }
  if (
    row.status !== 'queued' && row.status !== 'already_queued'
    && row.status !== 'no_symbols' && row.status !== 'unavailable'
  ) throw new TypeError('Refresh status is invalid')
  if (!Array.isArray(row.job_ids) || !row.job_ids.every(
    (jobId) => typeof jobId === 'string' && uuidPattern.test(jobId),
  )) throw new TypeError('Refresh job IDs are invalid')
  if (!Number.isSafeInteger(row.symbol_count) || Number(row.symbol_count) < 0) {
    throw new TypeError('Refresh symbol count is invalid')
  }
  if (typeof row.requested_at !== 'string') throw new TypeError('Refresh request time is invalid')
  parseAwareInstant(row.requested_at)
  if (row.data_cutoff !== null) {
    if (typeof row.data_cutoff !== 'string') throw new TypeError('Refresh data cutoff is invalid')
    parseAwareInstant(row.data_cutoff)
  }
  if (row.timeframe !== null && row.timeframe !== '1Min' && row.timeframe !== '1Day') {
    throw new TypeError('Refresh timeframe is invalid')
  }
  if (row.feed !== null && row.feed !== 'IEX') throw new TypeError('Refresh feed is invalid')
  if (typeof row.message !== 'string') throw new TypeError('Refresh message is invalid')

  const hasSession = row.data_cutoff !== null && row.timeframe !== null && row.feed === 'IEX'
  const hasNoSession = row.data_cutoff === null && row.timeframe === null && row.feed === null
  if (row.status === 'queued' || row.status === 'already_queued') {
    if (Number(row.symbol_count) === 0 || row.job_ids.length === 0 || !hasSession) {
      throw new TypeError('Queued refresh response is contradictory')
    }
  } else if (row.status === 'no_symbols') {
    if (
      Number(row.symbol_count) !== 0 || row.job_ids.length !== 0
      || row.data_cutoff !== null || row.timeframe !== null || row.feed !== 'IEX'
    ) throw new TypeError('Empty refresh response is contradictory')
  } else if (row.job_ids.length !== 0 || (!hasSession && !hasNoSession)) {
    throw new TypeError('Unavailable refresh response is contradictory')
  }

  return {
    dataCutoff: row.data_cutoff,
    feed: row.feed,
    jobIds: row.job_ids,
    message: row.message,
    requestedAt: row.requested_at,
    status: row.status,
    symbolCount: Number(row.symbol_count),
    timeframe: row.timeframe,
  }
}

export async function refreshWatchlistMarketData(
  options: WatchlistClientOptions,
): Promise<WatchlistRefreshResult> {
  if (typeof options.adminToken !== 'string' || !options.adminToken.trim()) {
    throw new WatchlistApiError('contract', 'Watchlist API authorization is unavailable')
  }
  const response = await request(options, '/api/v1/watchlist/refresh-market-data', {
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${options.adminToken}`,
    },
    method: 'POST',
  })
  if (response.status !== 202) {
    throw new WatchlistApiError(
      'contract', 'Watchlist API returned an invalid refresh status', response.status,
    )
  }
  try {
    return parseRefreshResponse(await response.json())
  } catch {
    throw new WatchlistApiError('contract', 'Watchlist API returned an invalid refresh response')
  }
}
