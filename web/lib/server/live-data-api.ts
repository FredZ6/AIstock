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
  cash: null | { balance: string; currency: 'USD' }
  cashLedger: JsonRecord[]
  configuration: null | { currency: 'USD'; id: string; initialCash: string; name: string }
  fills: JsonRecord[]
  initializedAt: string | null
  latestNav: null | { eventTime: string; nav: string; portfolioId: string }
  orders: JsonRecord[]
  performanceHistory: JsonRecord[]
  positions: JsonRecord[]
  riskDecisions: JsonRecord[]
  status: 'EMPTY' | 'SUCCESS'
  trading: 'paper_only'
}

export type PortfolioInitialization = {
  currency: 'USD'
  initialCash: string
  initializedAt: string
  name: string
  portfolioId: string
  status: 'READY'
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

export type PagedRecords = { items: JsonRecord[]; nextCursor: string | null }

export type WeeklyReviewDetail = {
  approvals: Array<{ action: 'APPROVE' | 'REJECT'; actorId: string; id: string; lessonId: string }>
  attributions: Array<{ category: string; controllable: boolean; id: string; outcomeId: string; rationale: string }>
  calibration: Array<{ calibrationError: string; confidence: string; decisionId: string; realizedReturn: string | null; status: 'PENDING' | 'MATURED' }>
  lessons: Array<{ confidence: string; id: string; replayDelta: string; statement: string; status: 'CANDIDATE' | 'APPROVED' | 'REJECTED' }>
  outcomes: Array<{ confidence: string; decisionId: string; id: string; opinion: 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'ABSTAIN'; returns: Record<string, string>; status: 'PENDING' | 'MATURED'; symbol: string }>
  replays: Array<{ dataCutoff: string; delta: string; id: string; lessonId: string }>
  review: { dataCutoff: string; id: string; status: 'RUNNING' | 'COMPLETED' | 'FAILED' }
}

export type ResearchRun = {
  dataCutoff: string
  decisionTime: string
  runId: string
  runType: 'RESEARCH' | 'PORTFOLIO'
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  symbol: string | null
}

export type LiveDataApiErrorKind = 'contract' | 'response' | 'unavailable'

export class LiveDataApiError extends Error {
  readonly correlationId?: string
  readonly kind: LiveDataApiErrorKind
  readonly status?: number

  constructor(kind: LiveDataApiErrorKind, message: string, status?: number, correlationId?: string) {
    super(message)
    this.name = 'LiveDataApiError'
    this.correlationId = correlationId
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

async function requestJson(
  options: LiveDataClientOptions,
  path: string,
  init: Omit<RequestInit, 'headers'> & { headers?: Record<string, string> } = {},
): Promise<unknown> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 5_000)
  let response: Response
  try {
    response = await (options.fetchImpl ?? fetch)(new URL(path, options.baseUrl).toString(), {
      ...init,
      cache: 'no-store',
      headers: { Accept: 'application/json', ...init.headers },
      signal: controller.signal,
    })
  } catch {
    throw new LiveDataApiError('unavailable', 'Live data API is unavailable')
  } finally {
    clearTimeout(timeout)
  }
  if (!response.ok) {
    throw new LiveDataApiError(
      'response',
      `Live data API returned HTTP ${response.status}`,
      response.status,
      response.headers.get('x-correlation-id') ?? undefined,
    )
  }
  try {
    return await response.json()
  } catch {
    throw new LiveDataApiError(
      'contract',
      'Live data API returned invalid JSON',
      response.status,
      response.headers.get('x-correlation-id') ?? undefined,
    )
  }
}

export async function initializePortfolio(
  options: LiveDataClientOptions,
  idempotencyKey: string,
): Promise<PortfolioInitialization> {
  if (!idempotencyKey) throw new LiveDataApiError('contract', 'Idempotency key is required')
  const value = await requestJson(options, '/api/v1/portfolio/initialize', {
    body: JSON.stringify({ effective_at: options.decisionTime }),
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
    method: 'POST',
  })
  return contract(() => {
    const source = record(value, 'portfolio_initialization')
    return {
      status: enumeration(source.status, ['READY'] as const, 'portfolio_initialization.status'),
      portfolioId: text(source.portfolio_id, 'portfolio_initialization.portfolio_id'),
      name: text(source.name, 'portfolio_initialization.name'),
      initialCash: decimal(source.initial_cash, 'portfolio_initialization.initial_cash'),
      currency: enumeration(source.currency, ['USD'] as const, 'portfolio_initialization.currency'),
      initializedAt: instant(source.initialized_at, 'portfolio_initialization.initialized_at'),
    }
  })
}

function contract<T>(parse: () => T): T {
  try {
    return parse()
  } catch (error) {
    if (error instanceof LiveDataApiError) throw error
    throw new LiveDataApiError('contract', 'Live data API returned an invalid response')
  }
}

function pagedRecords(value: unknown, path: string): PagedRecords {
  return contract(() => {
    const source = record(value, path)
    if (!Array.isArray(source.items)) throw new TypeError(`${path}.items must be an array`)
    const nextCursor = source.next_cursor
    if (nextCursor !== null && typeof nextCursor !== 'string') throw new TypeError(`${path}.next_cursor is invalid`)
    return {
      items: source.items.map((item, index) => record(item, `${path}.items[${index}]`)),
      nextCursor,
    }
  })
}

export async function getAlerts(options: LiveDataClientOptions): Promise<PagedRecords> {
  const query = new URLSearchParams({ decision_time: options.decisionTime, limit: '50' })
  return pagedRecords(await requestJson(options, `/api/v1/alerts?${query}`), 'alerts')
}

export async function getWeeklyReviews(options: LiveDataClientOptions): Promise<PagedRecords> {
  const query = new URLSearchParams({ decision_time: options.decisionTime, limit: '50' })
  return pagedRecords(await requestJson(options, `/api/v1/weekly-reviews?${query}`), 'weekly_reviews')
}

export async function getWeeklyReviewDetail(
  options: LiveDataClientOptions,
  reviewId: string,
): Promise<WeeklyReviewDetail> {
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  const value = await requestJson(options, `/api/v1/weekly-reviews/${encodeURIComponent(reviewId)}?${query}`)
  return contract(() => {
    const source = record(value, 'weekly_review')
    const rows = (name: string): JsonRecord[] => {
      const value = source[name]
      if (!Array.isArray(value)) throw new TypeError(`weekly_review.${name} must be an array`)
      return value.map((item, index) => record(item, `weekly_review.${name}[${index}]`))
    }
    const review = record(source.review, 'weekly_review.review')
    return {
      review: {
        id: text(review.id, 'weekly_review.review.id'),
        status: enumeration(review.status, ['RUNNING', 'COMPLETED', 'FAILED'] as const, 'weekly_review.review.status'),
        dataCutoff: instant(review.data_cutoff, 'weekly_review.review.data_cutoff'),
      },
      outcomes: rows('outcomes').map((item) => {
        const values = record(item.returns, 'weekly_review.outcome.returns')
        return {
          id: text(item.id, 'weekly_review.outcome.id'),
          decisionId: text(item.decision_id, 'weekly_review.outcome.decision_id'),
          symbol: text(item.symbol, 'weekly_review.outcome.symbol'),
          opinion: enumeration(item.opinion, ['BULLISH', 'NEUTRAL', 'BEARISH', 'ABSTAIN'] as const, 'weekly_review.outcome.opinion'),
          confidence: decimal(item.confidence, 'weekly_review.outcome.confidence'),
          status: enumeration(item.status, ['PENDING', 'MATURED'] as const, 'weekly_review.outcome.status'),
          returns: Object.fromEntries(Object.entries(values).map(([key, value]) => [key, decimal(value, `weekly_review.outcome.returns.${key}`)])),
        }
      }),
      attributions: rows('attributions').map((item) => ({
        id: text(item.id, 'weekly_review.attribution.id'),
        outcomeId: text(item.outcome_id, 'weekly_review.attribution.outcome_id'),
        category: text(item.category, 'weekly_review.attribution.category'),
        rationale: text(item.rationale, 'weekly_review.attribution.rationale'),
        controllable: configured(item.controllable, 'weekly_review.attribution.controllable'),
      })),
      lessons: rows('lessons').map((item) => ({
        id: text(item.id, 'weekly_review.lesson.id'),
        statement: text(item.statement, 'weekly_review.lesson.statement'),
        confidence: decimal(item.confidence, 'weekly_review.lesson.confidence'),
        replayDelta: decimal(item.replay_delta, 'weekly_review.lesson.replay_delta'),
        status: enumeration(item.status, ['CANDIDATE', 'APPROVED', 'REJECTED'] as const, 'weekly_review.lesson.status'),
      })),
      approvals: rows('approvals').map((item) => ({
        id: text(item.id, 'weekly_review.approval.id'),
        lessonId: text(item.lesson_id, 'weekly_review.approval.lesson_id'),
        actorId: text(item.actor_id, 'weekly_review.approval.actor_id'),
        action: enumeration(item.action, ['APPROVE', 'REJECT'] as const, 'weekly_review.approval.action'),
      })),
      replays: rows('replays').map((item) => ({
        id: text(item.id, 'weekly_review.replay.id'),
        lessonId: text(item.lesson_id, 'weekly_review.replay.lesson_id'),
        delta: decimal(item.delta, 'weekly_review.replay.delta'),
        dataCutoff: instant(item.data_cutoff, 'weekly_review.replay.data_cutoff'),
      })),
      calibration: rows('calibration').map((item) => ({
        decisionId: text(item.decision_id, 'weekly_review.calibration.decision_id'),
        confidence: decimal(item.confidence, 'weekly_review.calibration.confidence'),
        status: enumeration(item.status, ['PENDING', 'MATURED'] as const, 'weekly_review.calibration.status'),
        realizedReturn: item.realized_return === null ? null : decimal(item.realized_return, 'weekly_review.calibration.realized_return'),
        calibrationError: decimal(item.calibration_error, 'weekly_review.calibration.calibration_error'),
      })),
    }
  })
}

export async function getEvalRuns(options: LiveDataClientOptions): Promise<PagedRecords> {
  const query = new URLSearchParams({ decision_time: options.decisionTime, limit: '50' })
  return pagedRecords(await requestJson(options, `/api/v1/evals/runs?${query}`), 'eval_runs')
}

export async function getResearchRun(options: LiveDataClientOptions, runId: string): Promise<ResearchRun> {
  const value = await requestJson(options, `/api/v1/research-runs/${encodeURIComponent(runId)}`)
  return contract(() => {
    const source = record(value, 'research_run')
    return {
      runId: text(source.run_id, 'research_run.run_id'),
      runType: enumeration(source.run_type, ['RESEARCH', 'PORTFOLIO'] as const, 'research_run.run_type'),
      status: enumeration(source.status, ['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'] as const, 'research_run.status'),
      symbol: source.symbol === null ? null : text(source.symbol, 'research_run.symbol'),
      decisionTime: instant(source.decision_time, 'research_run.decision_time'),
      dataCutoff: instant(source.data_cutoff, 'research_run.data_cutoff'),
    }
  })
}

export async function getMarketQuotes(
  options: LiveDataClientOptions,
  symbols: string[],
): Promise<{
  decisionTime: string
  items: MarketQuote[]
  missingSymbols: string[]
  status: LiveDataStatus
}> {
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
    if (!Array.isArray(source.missing_symbols)) throw new TypeError('quotes.missing_symbols must be an array')
    return {
      status: enumeration(source.status, ['SUCCESS', 'DEGRADED', 'FAILURE'] as const, 'quotes.status'),
      decisionTime: instant(source.decision_time, 'quotes.decision_time'),
      missingSymbols: source.missing_symbols.map((value, index) => {
        const symbol = text(value, `quotes.missing_symbols[${index}]`)
        if (!symbolPattern.test(symbol)) throw new TypeError('missing quote symbol is invalid')
        return symbol
      }),
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
        status: row.status === undefined || row.status === null
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
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  const value = await requestJson(options, `/api/v1/portfolio?${query}`)
  return contract(() => {
    const source = record(value, 'portfolio')
    const latest = source.latest_nav === null ? null : record(source.latest_nav, 'portfolio.latest_nav')
    const configuration = source.configuration === null
      ? null
      : record(source.configuration, 'portfolio.configuration')
    const cash = source.cash === null ? null : record(source.cash, 'portfolio.cash')
    const records = (name: string): JsonRecord[] => {
      const value = source[name]
      if (!Array.isArray(value)) throw new TypeError(`portfolio.${name} must be an array`)
      return value.map((item, index) => record(item, `portfolio.${name}[${index}]`))
    }
    return {
      status: enumeration(source.status, ['EMPTY', 'SUCCESS'] as const, 'portfolio.status'),
      trading: enumeration(source.trading, ['paper_only'] as const, 'portfolio.trading'),
      configuration: configuration ? {
        id: text(configuration.id, 'portfolio.configuration.id'),
        name: text(configuration.name, 'portfolio.configuration.name'),
        initialCash: decimal(configuration.initial_cash, 'portfolio.configuration.initial_cash'),
        currency: enumeration(configuration.currency, ['USD'] as const, 'portfolio.configuration.currency'),
      } : null,
      initializedAt: source.initialized_at === null
        ? null
        : instant(source.initialized_at, 'portfolio.initialized_at'),
      cash: cash ? {
        balance: decimal(cash.balance, 'portfolio.cash.balance'),
        currency: enumeration(cash.currency, ['USD'] as const, 'portfolio.cash.currency'),
      } : null,
      latestNav: latest ? {
        eventTime: instant(latest.event_time, 'portfolio.latest_nav.event_time'),
        nav: decimal(latest.nav, 'portfolio.latest_nav.nav'),
        portfolioId: text(latest.portfolio_id, 'portfolio.latest_nav.portfolio_id'),
      } : null,
      positions: records('positions'),
      riskDecisions: records('risk_decisions'),
      orders: records('orders'),
      fills: records('fills'),
      cashLedger: records('cash_ledger'),
      performanceHistory: records('performance_history'),
    }
  })
}

export async function getStockResearch(
  options: LiveDataClientOptions,
  symbol: string,
): Promise<ResearchRecord[]> {
  if (!symbolPattern.test(symbol)) throw new LiveDataApiError('contract', 'Research symbol is invalid')
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  const value = await requestJson(options, `/api/v1/stocks/${encodeURIComponent(symbol)}/research?${query}`)
  return contract(() => {
    const page = record(value, 'research')
    if (!Array.isArray(page.items)) throw new TypeError('research.items must be an array')
    return page.items.map((item, index) => {
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
