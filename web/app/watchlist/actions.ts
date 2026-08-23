'use server'

import { revalidatePath } from 'next/cache'

import { readApiBaseUrl, readWebDataMode } from '../../lib/server/data-mode'
import {
  addWatchlistItem,
  deleteWatchlistItem,
  patchWatchlistItem,
  type WatchlistClientOptions,
} from '../../lib/server/watchlist-api'
import type { WatchlistActionState } from '../../lib/watchlist-action-state'

const decimalPattern = /^-?\d+(?:\.\d+)?$/
const symbolPattern = /^[A-Z.]{1,10}$/
const persistenceError = 'Unable to persist watchlist changes. Try again.'

function clientOptions(): WatchlistClientOptions {
  if (readWebDataMode(process.env) !== 'api') {
    throw new TypeError('Watchlist persistence requires API mode')
  }
  return { baseUrl: readApiBaseUrl(process.env) }
}

function normalizedSymbol(value: FormDataEntryValue | null): string {
  return typeof value === 'string' ? value.trim().toUpperCase() : ''
}

function invalidSymbol(symbol: string): WatchlistActionState | null {
  return symbolPattern.test(symbol)
    ? null
    : { message: 'Symbol must match [A-Z.]{1,10}', status: 'error', symbol }
}

function failed(symbol: string): WatchlistActionState {
  return { message: persistenceError, status: 'error', symbol }
}

export async function addWatchlistAction(
  _previousState: WatchlistActionState,
  formData: FormData,
): Promise<WatchlistActionState> {
  const symbol = normalizedSymbol(formData.get('symbol'))
  const invalid = invalidSymbol(symbol)
  if (invalid) return invalid

  try {
    await addWatchlistItem(clientOptions(), {
      dailyResearch: formData.get('daily_research') === 'on',
      intradayMonitoring: formData.get('intraday_monitoring') === 'on',
      symbol,
      thresholds: {},
    })
  } catch {
    return failed(symbol)
  }

  revalidatePath('/watchlist')
  return { message: `${symbol} added.`, status: 'success', symbol }
}

export async function updateWatchlistAction(
  symbolValue: string,
  _previousState: WatchlistActionState,
  formData: FormData,
): Promise<WatchlistActionState> {
  const symbol = symbolValue.trim().toUpperCase()
  const invalid = invalidSymbol(symbol)
  if (invalid) return invalid
  const threshold = formData.get('alert_threshold')
  if (typeof threshold !== 'string' || (threshold !== '' && !decimalPattern.test(threshold))) {
    return { message: 'Alert threshold must be a Decimal string', status: 'error', symbol }
  }

  try {
    await patchWatchlistItem(clientOptions(), symbol, {
      dailyResearch: formData.get('daily_research') === 'on',
      intradayMonitoring: formData.get('intraday_monitoring') === 'on',
      thresholds: threshold === '' ? {} : { return_5m: threshold },
    })
  } catch {
    return failed(symbol)
  }

  revalidatePath('/watchlist')
  return { message: `${symbol} updated.`, status: 'success', symbol }
}

export async function deleteWatchlistAction(
  symbolValue: string,
  _previousState: WatchlistActionState,
  _formData: FormData,
): Promise<WatchlistActionState> {
  void _previousState
  void _formData
  const symbol = symbolValue.trim().toUpperCase()
  const invalid = invalidSymbol(symbol)
  if (invalid) return invalid

  try {
    await deleteWatchlistItem(clientOptions(), symbol)
  } catch {
    return failed(symbol)
  }

  revalidatePath('/watchlist')
  return { message: `${symbol} deleted.`, status: 'success', symbol }
}
