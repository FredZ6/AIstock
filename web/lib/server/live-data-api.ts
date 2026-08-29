import 'server-only'

import { parseAwareInstant } from '../time'

type Fetch = typeof fetch
type JsonRecord = Record<string, unknown>

export type LiveDataStatus = 'SUCCESS' | 'DEGRADED' | 'FAILURE'

export type MarketQuote = {
  availableAt: string
  close: string
  coverage: 'IEX' | 'SIP'
  eventTime: string
  provider: string
  symbol: string
}

export type ProviderHealth = {
  mode: 'fixture' | 'paper' | 'test'
  providers: Record<string, {
    configured: boolean
    coverage?: string | null
    mode: 'fixture' | 'read_only' | 'unavailable'
    status?: 'SUCCESS' | 'DEGRADED' | 'FAILURE' | 'UNAVAILABLE'
  }>
}

export type PortfolioSummary = {
  latestNav: null | { eventTime: string; nav: string; portfolioId: string }
  trading: 'paper_only'
}

export type ResearchRecord = {
  asOf: string
  confidence: string
  direction: string
  horizon: string
  id: string
  opinion: 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'ABSTAIN' | null
  summary: string
  symbol: string
}

export type LiveDataClientOptions = {
  baseUrl: string
  decisionTime: string
  fetchImpl?: Fetch
  timeoutMs?: number
}

export type LiveDataApiErrorKind = 'contract' | 'response' | 'unavailable'

export class LiveDataApiError extends Error {
  readonly kind: LiveDataApiErrorKind
  readonly status?: number

  constructor(kind: LiveDataApiErrorKind, message: string, status?: number) {
    super(message)
    this.name = 'LiveDataApiError'
    this.kind = kind
    this.status = status
  }
}

const decimalPattern = /^-?\d+(?:\.\d+)?$/
const symbolPattern = /^[A-Z.]{1,10}$/

function record(value: unknown, path: string): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new TypeError(`${path} must be an object`)
  }
  return value as JsonRecord
}

function text(value: unknown, path: string): string {
  if (typeof value !== 'string' || value.length === 0) throw new TypeError(`${path} must be text`)
  return value
}

function decimal(value: unknown, path: string): string {
  const result = text(value, path)
  if (!decimalPattern.test(result)) throw new TypeError(`${path} must be a Decimal string`)
  return result
}

function instant(value: unknown, path: string): string {
  const result = text(value, path)
  parseAwareInstant(result)
  return result
}

function enumeration<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) throw new TypeError(`${path} is invalid`)
  return value as T
}

function configured(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') throw new TypeError(`${path} must be boolean`)
  return value
}

async function requestJson(options: LiveDataClientOptions, path: string): Promise<unknown> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 5_000)
  let response: Response
  try {
    response = await (options.fetchImpl ?? fetch)(new URL(path, options.baseUrl).toString(), {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
  } catch {
    throw new LiveDataApiError('unavailable', 'Live data API is unavailable')
  } finally {
    clearTimeout(timeout)
  }
  if (!response.ok) {
    throw new LiveDataApiError('response', `Live data API returned HTTP ${response.status}`, response.status)
  }
  try {
    return await response.json()
  } catch {
    throw new LiveDataApiError('contract', 'Live data API returned invalid JSON')
  }
}

function contract<T>(parse: () => T): T {
  try {
    return parse()
  } catch (error) {
    if (error instanceof LiveDataApiError) throw error
    throw new LiveDataApiError('contract', 'Live data API returned an invalid response')
  }
}

export async function getMarketQuotes(
  options: LiveDataClientOptions,
  symbols: string[],
): Promise<{ decisionTime: string; items: MarketQuote[]; status: LiveDataStatus }> {
  if (!symbols.length || symbols.some((symbol) => !symbolPattern.test(symbol))) {
    throw new LiveDataApiError('contract', 'Quote symbols are invalid')
  }
  const query = new URLSearchParams({
    decision_time: options.decisionTime,
    symbols: symbols.join(','),
  })
  const value = await requestJson(options, `/api/v1/market-data/quotes?${query}`)
  return contract(() => {
    const source = record(value, 'quotes')
    if (!Array.isArray(source.items)) throw new TypeError('quotes.items must be an array')
    return {
      status: enumeration(source.status, ['SUCCESS', 'DEGRADED', 'FAILURE'] as const, 'quotes.status'),
      decisionTime: instant(source.decision_time, 'quotes.decision_time'),
      items: source.items.map((item, index) => {
        const row = record(item, `quotes.items[${index}]`)
        const symbol = text(row.symbol, 'quote.symbol')
        if (!symbolPattern.test(symbol)) throw new TypeError('quote.symbol is invalid')
        return {
          symbol,
          close: decimal(row.close, 'quote.close'),
          provider: text(row.provider, 'quote.provider'),
          coverage: enumeration(row.coverage, ['IEX', 'SIP'] as const, 'quote.coverage'),
          eventTime: instant(row.event_time, 'quote.event_time'),
          availableAt: instant(row.available_at, 'quote.available_at'),
        }
      }),
    }
  })
}

export async function getProviderHealth(options: LiveDataClientOptions): Promise<ProviderHealth> {
  const value = await requestJson(options, '/api/v1/providers/health')
  return contract(() => {
    const source = record(value, 'health')
    const rows = record(source.providers, 'health.providers')
    const providers: ProviderHealth['providers'] = {}
    for (const [name, value] of Object.entries(rows)) {
      const row = record(value, `health.providers.${name}`)
      providers[name] = {
        configured: configured(row.configured, `${name}.configured`),
        mode: enumeration(row.mode, ['fixture', 'read_only', 'unavailable'] as const, `${name}.mode`),
        coverage: row.coverage === undefined || row.coverage === null ? null : text(row.coverage, `${name}.coverage`),
        status: row.status === undefined
          ? undefined
          : enumeration(row.status, ['SUCCESS', 'DEGRADED', 'FAILURE', 'UNAVAILABLE'] as const, `${name}.status`),
      }
    }
    return {
      mode: enumeration(source.mode, ['fixture', 'paper', 'test'] as const, 'health.mode'),
      providers,
    }
  })
}

export async function getPortfolioSummary(options: LiveDataClientOptions): Promise<PortfolioSummary> {
  const value = await requestJson(options, '/api/v1/portfolio')
  return contract(() => {
    const source = record(value, 'portfolio')
    const latest = source.latest_nav === null ? null : record(source.latest_nav, 'portfolio.latest_nav')
    return {
      trading: enumeration(source.trading, ['paper_only'] as const, 'portfolio.trading'),
      latestNav: latest ? {
        eventTime: instant(latest.event_time, 'portfolio.latest_nav.event_time'),
        nav: decimal(latest.nav, 'portfolio.latest_nav.nav'),
        portfolioId: text(latest.portfolio_id, 'portfolio.latest_nav.portfolio_id'),
      } : null,
    }
  })
}

export async function getStockResearch(
  options: LiveDataClientOptions,
  symbol: string,
): Promise<ResearchRecord[]> {
  if (!symbolPattern.test(symbol)) throw new LiveDataApiError('contract', 'Research symbol is invalid')
  const value = await requestJson(options, `/api/v1/stocks/${encodeURIComponent(symbol)}/research`)
  return contract(() => {
    if (!Array.isArray(value)) throw new TypeError('research must be an array')
    return value.map((item, index) => {
      const row = record(item, `research[${index}]`)
      return {
        id: text(row.id, 'research.id'),
        symbol: text(row.symbol, 'research.symbol'),
        asOf: instant(row.as_of, 'research.as_of'),
        direction: text(row.direction, 'research.direction'),
        summary: text(row.summary, 'research.summary'),
        confidence: decimal(row.confidence, 'research.confidence'),
        horizon: text(row.horizon, 'research.horizon'),
        opinion: row.opinion === null
          ? null
          : enumeration(row.opinion, ['BULLISH', 'NEUTRAL', 'BEARISH', 'ABSTAIN'] as const, 'research.opinion'),
      }
    })
  })
}
