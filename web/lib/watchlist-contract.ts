import type { ApiWatchlistItem } from './product-types'
import { parseAwareInstant } from './time'

type JsonRecord = Record<string, unknown>

const decimalPattern = /^-?\d+(?:\.\d+)?$/
const symbolPattern = /^[A-Z.]{1,10}$/
const unavailableEnrichment = {
  kind: 'unavailable' as const,
  missing: ['market', 'research', 'earnings', 'data-quality'] as const,
}

function record(value: unknown, path: string): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new TypeError(`${path} must be an object`)
  }
  return value as JsonRecord
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') {
    throw new TypeError(`${path} must be boolean`)
  }
  return value
}

function awareDateTime(value: unknown, path: string): string {
  if (typeof value !== 'string') {
    throw new TypeError(`${path} must be a string`)
  }
  try {
    parseAwareInstant(value)
  } catch {
    throw new TypeError(`${path} must be an aware datetime`)
  }
  return value
}

function symbol(value: unknown, path: string): string {
  if (typeof value !== 'string' || !symbolPattern.test(value)) {
    throw new TypeError(`${path} must match [A-Z.]{1,10}`)
  }
  return value
}

function alertThreshold(thresholds: JsonRecord, path: string): string | null {
  for (const [name, threshold] of Object.entries(thresholds)) {
    if (typeof threshold !== 'string' || !decimalPattern.test(threshold)) {
      throw new TypeError(`${path}.${name} must be a Decimal string`)
    }
  }
  const value = thresholds.return_5m
  if (value === undefined) return null
  return value as string
}

export function parseWatchlistRow(value: unknown, path = 'watchlist item'): ApiWatchlistItem {
  const source = record(value, path)
  const thresholds = record(source.thresholds, `${path}.thresholds`)
  return {
    symbol: symbol(source.symbol, `${path}.symbol`),
    dailyResearch: boolean(source.daily_research, `${path}.daily_research`),
    intradayMonitoring: boolean(source.intraday_monitoring, `${path}.intraday_monitoring`),
    alertThreshold: alertThreshold(thresholds, `${path}.thresholds`),
    createdAt: awareDateTime(source.created_at, `${path}.created_at`),
    updatedAt: awareDateTime(source.updated_at, `${path}.updated_at`),
    enrichment: unavailableEnrichment,
  }
}

export function parseWatchlistRows(value: unknown): ApiWatchlistItem[] {
  if (!Array.isArray(value)) {
    throw new TypeError('watchlist must be an array')
  }
  return value.map((row, index) => parseWatchlistRow(row, `watchlist[${index}]`))
}
