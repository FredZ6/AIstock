import 'server-only'

import type { ApiWatchlistItem } from '../product-types'
import { parseWatchlistRows } from '../watchlist-contract'

type Fetch = typeof fetch

type WatchlistClientOptions = {
  baseUrl: string
  fetchImpl?: Fetch
  timeoutMs?: number
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

export async function listWatchlist({
  baseUrl,
  fetchImpl = fetch,
  timeoutMs = 5_000,
}: WatchlistClientOptions): Promise<ApiWatchlistItem[]> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  let response: Response

  try {
    response = await fetchImpl(new URL('/api/v1/watchlist', baseUrl).toString(), {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      method: 'GET',
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

  try {
    return parseWatchlistRows(await response.json())
  } catch {
    throw new WatchlistApiError('contract', 'Watchlist API returned an invalid response')
  }
}
