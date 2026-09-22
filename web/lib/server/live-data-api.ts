import 'server-only'

import { parseAwareInstant } from '../time'

type Fetch = typeof fetch
type JsonRecord = Record<string, unknown>

export type LiveDataStatus = 'SUCCESS' | 'DEGRADED' | 'FAILURE'

export type AlertRecord = {
  acknowledgedAt: string | null
  acknowledgedBy: string | null
  alertKey: string
  conditions: unknown[]
  correlationId: string
  createdAt: string
  dataQuality: JsonRecord
  eventTime: string
  id: string
  materiality: string
  metrics: JsonRecord
  ruleId: string
  ruleVersion: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  symbol: string
}

export type AlertPage = { items: AlertRecord[]; nextCursor: string | null }

export type EvalRunRecord = {
  caseCount: number
  confidencePolicyVersion: string
  createdAt: string
  dataCutoff: string
  datasetVersion: string
  executionPolicyVersion: string
  gatePolicyVersion: string
  id: string
  mode: 'fixture'
  modelVersion: string
  passed: boolean
  promptVersion: string
  researchScoringPolicyVersion: string
  riskPolicyVersion: string
  status: 'PASSED' | 'FAILED'
  summaryHash: string
}

export type EvalRunPage = { items: EvalRunRecord[]; nextCursor: string | null }

export type EvalRunDetail = {
  gates: Array<{ comparison: 'AT_LEAST' | 'AT_MOST' | 'LESS_THAN'; name: string; observed: string | null; passed: boolean; reason: string; threshold: string }>
  metrics: Array<{ caseHashes: string[]; caseIds: string[]; name: string; value: string }>
  run: EvalRunRecord
}

export type MarketQuote = {
  availableAt: string
  close: string
  coverage: 'IEX' | 'SIP'
  eventTime: string
  provider: string
  symbol: string
}

export type MarketBar = MarketQuote & {
  conflict: boolean
  contentHash: string
  feedType: string
  high: string
  ingestedAt: string
  low: string
  open: string
  rawObjectKey: string
  session: 'PRE_MARKET' | 'REGULAR' | 'AFTER_HOURS' | 'OVERNIGHT'
  timeframe: '1Min' | '1Day'
  volume: string
}

export type ProviderHealth = {
  mode: 'fixture' | 'paper' | 'test'
  providers: Record<string, {
    configured: boolean
    coverage?: string | null
    mode: 'fixture' | 'read_only' | 'unavailable'
    operatorAction?: string | null
    status?: 'SUCCESS' | 'DEGRADED' | 'FAILURE' | 'UNAVAILABLE'
  }>
}

export type PortfolioSummary = {
  cash: null | { balance: string; currency: 'USD' }
  cashLedger: Array<{
    account: string
    createdAt: string
    credit: string
    currency: 'USD'
    debit: string
    id: string
    idempotencyKey: string
    occurredAt: string
    reversalOfId: string | null
    sourceId: string
    transactionId: string
  }>
  configuration: null | { currency: 'USD'; id: string; initialCash: string; name: string }
  fills: Array<{
    createdAt: string
    currency: 'USD'
    executionPolicyVersionId: string
    fee: string
    filledAt: string
    id: string
    idempotencyKey: string
    orderId: string
    portfolioId: string
    price: string
    quantity: string
    reversalOfId: string | null
    side: 'BUY' | 'SELL'
    sourceBarTime: string
    symbol: string
  }>
  initializedAt: string | null
  latestNav: null | PortfolioNav
  orders: JsonRecord[]
  performanceHistory: PortfolioNav[]
  positions: Array<{
    averageCost: string
    marketPrice: string | null
    marketValue: string | null
    priceAvailableAt: string | null
    quantity: string
    symbol: string
    unrealizedPnl: string | null
  }>
  riskDecisions: Array<{
    approvedDelta: string
    approvedWeight: string
    authorizationSource: string
    authorizedSide: 'BUY' | 'SELL' | null
    createdAt: string
    currentWeight: string
    decidedAt: string
    id: string
    marketContextSnapshotId: string | null
    maxOrderQuantity: string
    portfolioId: string
    proposalId: string
    reasonCodes: string[]
    referenceNav: string | null
    referencePrice: string | null
    researchDecisionId: string | null
    requestedWeight: string
    riskPolicyVersionId: string
    status: 'APPROVED' | 'CLIPPED' | 'REJECTED'
    symbol: string
  }>
  status: 'EMPTY' | 'SUCCESS'
  trading: 'paper_only'
}

export type PortfolioNav = {
  availableAt: string
  eventTime: string
  id: string
  nav: string
  portfolioId: string
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

export type SecFiling = {
  acceptedAt: string
  accessionNumber: string
  availableAt: string
  description: string
  documentRawObjectKey: string
  contentHash: string
  eventTime: string
  filingDate: string
  form: string
  id: string
  provider: string
  rawObjectKey: string
  reportDate: string | null
}

export type FinancialFact = {
  accessionNumber: string
  availableAt: string
  canonicalConcept: string | null
  contentHash: string
  currency: string | null
  id: string
  eventTime: string
  mappingStatus: 'EXACT' | 'DERIVED' | 'UNMAPPED' | 'AMBIGUOUS'
  periodEnd: string
  periodStart: string
  provider: string
  rawObjectKey: string
  sourceConcept: string
  taxonomy: string
  unit: string
  value: string
}

export type NewsArticle = {
  availableAt: string
  contentHash: string
  eventTime: string
  headline: string
  id: string
  provider: string
  rawObjectKey: string
  source: string
  summary: string
}

export type EarningsEvent = {
  availableAt: string
  contentHash: string
  currency: string | null
  estimate: string | null
  eventDate: string
  eventTime: string
  fiscalDateEnd: string
  id: string
  provider: string
  rawObjectKey: string
}

export type OptionSnapshot = {
  availableAt: string
  contentHash: string
  eventTime: string
  feedType: string
  id: string
  payload: JsonRecord
  provider: string
  rawObjectKey: string
}

export type StockResearch = {
  earningsEvents: EarningsEvent[]
  financialFacts: FinancialFact[]
  newsArticles: NewsArticle[]
  optionSnapshots: OptionSnapshot[]
  records: ResearchRecord[]
  secFilings: SecFiling[]
  unavailableDomains: Array<'EARNINGS' | 'NEWS' | 'OPTIONS' | 'ANALYST_TARGETS'>
  unavailableReasons: Partial<Record<'EARNINGS' | 'NEWS' | 'OPTIONS' | 'ANALYST_TARGETS', string>>
}

export type DataQuality = {
  conflict: boolean
  coverage: 'IEX' | 'SIP' | null
  dataset: string
  delay: string | null
  dimension: string
  freshness: string | null
  id: string
  observedAt: string
  provider: string
  status: 'PASS' | 'DEGRADED' | 'UNAVAILABLE' | 'FAIL'
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

export type ResearchRunReport = {
  runId: string
  thesis: { id: string; symbol: string; asOf: string; direction: string; summary: string; catalysts: unknown[]; risks: unknown[]; invalidationConditions: unknown[]; horizon: string; confidence: string; supersedesThesisId: string | null; createdAt: string }
  opinion: { id: string; value: 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'ABSTAIN'; createdAt: string }
  decision: { id: string; dataCutoff: string; availableAt: string; promptVersion: string; modelVersion: string; policyVersions: { researchScoring: string; risk: string; execution: string; confidence: string }; createdAt: string }
  evidence: Array<{ id: string; relation: 'SUPPORTS' | 'CONTRADICTS' | 'CONTEXT'; weight: string; rationale: string; claims: string[]; provider: string; feedType: string; eventTime: string; availableAt: string; ingestedAt: string; contentHash: string; rawObjectKey: string }>
  evidenceGaps: Array<{ id: string; runId: string; kind: 'UNKNOWN' | 'MISSING' | 'UNAVAILABLE' | 'CONFLICTED'; field: string; domain: string; reason: string; provider: string | null; observedAt: string; createdAt: string }>
  decisionDiff: { id: string; decisionId: string; previousDecisionId: string | null; generator: 'DETERMINISTIC_CODE'; changes: JsonRecord; createdAt: string }
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

function booleanValue(value: unknown, path: string): boolean {
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

export async function getAlerts(options: LiveDataClientOptions): Promise<AlertPage> {
  const query = new URLSearchParams({ decision_time: options.decisionTime, limit: '50' })
  const value = await requestJson(options, `/api/v1/alerts?${query}`)
  return contract(() => {
    const source = record(value, 'alerts')
    if (!Array.isArray(source.items)) throw new TypeError('alerts.items must be an array')
    const nextCursor = source.next_cursor
    if (nextCursor !== null && typeof nextCursor !== 'string') throw new TypeError('alerts.next_cursor is invalid')
    return {
      items: source.items.map((item, index) => {
        const row = record(item, `alerts.items[${index}]`)
        const symbol = text(row.symbol, `alerts.items[${index}].symbol`)
        if (!symbolPattern.test(symbol)) throw new TypeError(`alerts.items[${index}].symbol is invalid`)
        if (!Array.isArray(row.conditions)) throw new TypeError(`alerts.items[${index}].conditions must be an array`)
        return {
          id: text(row.id, `alerts.items[${index}].id`),
          correlationId: text(row.correlation_id, `alerts.items[${index}].correlation_id`),
          alertKey: text(row.alert_key, `alerts.items[${index}].alert_key`),
          symbol,
          eventTime: instant(row.event_time, `alerts.items[${index}].event_time`),
          ruleId: text(row.rule_id, `alerts.items[${index}].rule_id`),
          ruleVersion: text(row.rule_version, `alerts.items[${index}].rule_version`),
          severity: enumeration(row.severity, ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const, `alerts.items[${index}].severity`),
          materiality: decimal(row.materiality, `alerts.items[${index}].materiality`),
          conditions: row.conditions,
          metrics: record(row.metrics, `alerts.items[${index}].metrics`),
          dataQuality: record(row.data_quality, `alerts.items[${index}].data_quality`),
          acknowledgedAt: row.acknowledged_at === null ? null : instant(row.acknowledged_at, `alerts.items[${index}].acknowledged_at`),
          acknowledgedBy: row.acknowledged_by === null ? null : text(row.acknowledged_by, `alerts.items[${index}].acknowledged_by`),
          createdAt: instant(row.created_at, `alerts.items[${index}].created_at`),
        }
      }),
      nextCursor,
    }
  })
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
        controllable: booleanValue(item.controllable, 'weekly_review.attribution.controllable'),
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

function stringArray(value: unknown, path: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new TypeError(`${path} must be an array of strings`)
  }
  return value
}

function evalRun(value: unknown, path: string): EvalRunRecord {
  const row = record(value, path)
  if (!Number.isInteger(row.case_count) || Number(row.case_count) < 1) {
    throw new TypeError(`${path}.case_count is invalid`)
  }
  const summaryHash = text(row.summary_hash, `${path}.summary_hash`)
  if (!/^[0-9a-f]{64}$/.test(summaryHash)) throw new TypeError(`${path}.summary_hash is invalid`)
  return {
    id: text(row.id, `${path}.id`),
    status: enumeration(row.status, ['PASSED', 'FAILED'] as const, `${path}.status`),
    passed: booleanValue(row.passed, `${path}.passed`),
    mode: enumeration(row.mode, ['fixture'] as const, `${path}.mode`),
    datasetVersion: text(row.dataset_version, `${path}.dataset_version`),
    caseCount: Number(row.case_count),
    dataCutoff: instant(row.data_cutoff, `${path}.data_cutoff`),
    modelVersion: text(row.model_version, `${path}.model_version`),
    promptVersion: text(row.prompt_version, `${path}.prompt_version`),
    researchScoringPolicyVersion: text(row.research_scoring_policy_version, `${path}.research_scoring_policy_version`),
    riskPolicyVersion: text(row.risk_policy_version, `${path}.risk_policy_version`),
    executionPolicyVersion: text(row.execution_policy_version, `${path}.execution_policy_version`),
    confidencePolicyVersion: text(row.confidence_policy_version, `${path}.confidence_policy_version`),
    gatePolicyVersion: text(row.gate_policy_version, `${path}.gate_policy_version`),
    summaryHash,
    createdAt: instant(row.created_at, `${path}.created_at`),
  }
}

export async function getEvalRuns(options: LiveDataClientOptions): Promise<EvalRunPage> {
  const query = new URLSearchParams({ decision_time: options.decisionTime, limit: '50' })
  const value = await requestJson(options, `/api/v1/evals/runs?${query}`)
  return contract(() => {
    const source = record(value, 'eval_runs')
    if (!Array.isArray(source.items)) throw new TypeError('eval_runs.items must be an array')
    const nextCursor = source.next_cursor
    if (nextCursor !== null && typeof nextCursor !== 'string') throw new TypeError('eval_runs.next_cursor is invalid')
    return { items: source.items.map((item, index) => evalRun(item, `eval_runs.items[${index}]`)), nextCursor }
  })
}

export async function getEvalRunDetail(options: LiveDataClientOptions, runId: string): Promise<EvalRunDetail> {
  if (!runId) throw new LiveDataApiError('contract', 'Evaluation run id is required')
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  const value = await requestJson(options, `/api/v1/evals/runs/${encodeURIComponent(runId)}?${query}`)
  return contract(() => {
    const source = record(value, 'eval_run_detail')
    if (!Array.isArray(source.metrics) || !Array.isArray(source.gates)) throw new TypeError('evaluation evidence must be arrays')
    return {
      run: evalRun(source.run, 'eval_run_detail.run'),
      metrics: source.metrics.map((item, index) => {
        const row = record(item, `eval_run_detail.metrics[${index}]`)
        return { name: text(row.metric_name, 'metric.name'), value: decimal(row.metric_value, 'metric.value'), caseIds: stringArray(row.case_ids, 'metric.case_ids'), caseHashes: stringArray(row.case_hashes, 'metric.case_hashes') }
      }),
      gates: source.gates.map((item, index) => {
        const row = record(item, `eval_run_detail.gates[${index}]`)
        return { name: text(row.metric_name, 'gate.name'), comparison: enumeration(row.comparison, ['AT_LEAST', 'AT_MOST', 'LESS_THAN'] as const, 'gate.comparison'), threshold: decimal(row.threshold, 'gate.threshold'), observed: row.observed === null ? null : decimal(row.observed, 'gate.observed'), passed: booleanValue(row.passed, 'gate.passed'), reason: text(row.reason, 'gate.reason') }
      }),
    }
  })
}

function researchRun(value: unknown): ResearchRun {
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

export async function createResearchRun(
  options: LiveDataClientOptions,
  symbol: string,
  idempotencyKey: string,
): Promise<ResearchRun> {
  if (!symbolPattern.test(symbol)) {
    throw new LiveDataApiError('contract', 'Research symbol is invalid')
  }
  if (!idempotencyKey) {
    throw new LiveDataApiError('contract', 'Idempotency key is required')
  }
  try {
    parseAwareInstant(options.decisionTime)
  } catch {
    throw new LiveDataApiError('contract', 'Decision time must include a timezone')
  }
  return researchRun(await requestJson(options, '/api/v1/research-runs', {
    body: JSON.stringify({
      data_cutoff: options.decisionTime,
      decision_time: options.decisionTime,
      symbol,
    }),
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
    method: 'POST',
  }))
}

export async function getResearchRun(options: LiveDataClientOptions, runId: string): Promise<ResearchRun> {
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  return researchRun(await requestJson(
    options,
    `/api/v1/research-runs/${encodeURIComponent(runId)}?${query}`,
  ))
}

export async function getLatestResearchRun(options: LiveDataClientOptions): Promise<ResearchRun> {
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  return researchRun(await requestJson(options, `/api/v1/research-runs/latest?${query}`))
}

export async function getResearchRunReport(
  options: LiveDataClientOptions,
  runId: string,
): Promise<ResearchRunReport> {
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  const value = await requestJson(options, `/api/v1/research-runs/${encodeURIComponent(runId)}/report?${query}`)
  return contract(() => {
    const source = record(value, 'research_report')
    const thesis = record(source.thesis, 'research_report.thesis')
    const opinion = record(source.opinion, 'research_report.opinion')
    const decision = record(source.decision, 'research_report.decision')
    const policies = record(decision.policy_versions, 'research_report.decision.policy_versions')
    const diff = record(source.decision_diff, 'research_report.decision_diff')
    if (!Array.isArray(source.evidence) || !Array.isArray(source.evidence_gaps)) {
      throw new TypeError('research_report evidence collections must be arrays')
    }
    const unknowns = (input: unknown, path: string): unknown[] => {
      if (!Array.isArray(input)) throw new TypeError(`${path} must be an array`)
      return input
    }
    const strings = (input: unknown, path: string): string[] => unknowns(input, path)
      .map((item, index) => text(item, `${path}[${index}]`))
    const nullableText = (input: unknown, path: string): string | null => input === null ? null : text(input, path)
    return {
      runId: text(source.run_id, 'research_report.run_id'),
      thesis: {
        id: text(thesis.id, 'research_report.thesis.id'), symbol: text(thesis.symbol, 'research_report.thesis.symbol'),
        asOf: instant(thesis.as_of, 'research_report.thesis.as_of'), direction: text(thesis.direction, 'research_report.thesis.direction'),
        summary: text(thesis.summary, 'research_report.thesis.summary'), catalysts: unknowns(thesis.catalysts, 'research_report.thesis.catalysts'),
        risks: unknowns(thesis.risks, 'research_report.thesis.risks'), invalidationConditions: unknowns(thesis.invalidation_conditions, 'research_report.thesis.invalidation_conditions'),
        horizon: text(thesis.horizon, 'research_report.thesis.horizon'), confidence: decimal(thesis.confidence, 'research_report.thesis.confidence'),
        supersedesThesisId: nullableText(thesis.supersedes_thesis_id, 'research_report.thesis.supersedes_thesis_id'),
        createdAt: instant(thesis.created_at, 'research_report.thesis.created_at'),
      },
      opinion: { id: text(opinion.id, 'research_report.opinion.id'), value: enumeration(opinion.value, ['BULLISH', 'NEUTRAL', 'BEARISH', 'ABSTAIN'] as const, 'research_report.opinion.value'), createdAt: instant(opinion.created_at, 'research_report.opinion.created_at') },
      decision: {
        id: text(decision.id, 'research_report.decision.id'), dataCutoff: instant(decision.data_cutoff, 'research_report.decision.data_cutoff'),
        availableAt: instant(decision.available_at, 'research_report.decision.available_at'), promptVersion: text(decision.prompt_version, 'research_report.decision.prompt_version'),
        modelVersion: text(decision.model_version, 'research_report.decision.model_version'), createdAt: instant(decision.created_at, 'research_report.decision.created_at'),
        policyVersions: { researchScoring: text(policies.research_scoring, 'research_report.decision.policy_versions.research_scoring'), risk: text(policies.risk, 'research_report.decision.policy_versions.risk'), execution: text(policies.execution, 'research_report.decision.policy_versions.execution'), confidence: text(policies.confidence, 'research_report.decision.policy_versions.confidence') },
      },
      evidence: source.evidence.map((item, index) => {
        const row = record(item, `research_report.evidence[${index}]`)
        return { id: text(row.id, 'evidence.id'), relation: enumeration(row.relation, ['SUPPORTS', 'CONTRADICTS', 'CONTEXT'] as const, 'evidence.relation'), weight: decimal(row.weight, 'evidence.weight'), rationale: text(row.rationale, 'evidence.rationale'), claims: strings(row.claims, 'evidence.claims'), provider: text(row.provider, 'evidence.provider'), feedType: text(row.feed_type, 'evidence.feed_type'), eventTime: instant(row.event_time, 'evidence.event_time'), availableAt: instant(row.available_at, 'evidence.available_at'), ingestedAt: instant(row.ingested_at, 'evidence.ingested_at'), contentHash: text(row.content_hash, 'evidence.content_hash'), rawObjectKey: text(row.raw_object_key, 'evidence.raw_object_key') }
      }),
      evidenceGaps: source.evidence_gaps.map((item, index) => {
        const row = record(item, `research_report.evidence_gaps[${index}]`)
        return { id: text(row.id, 'gap.id'), runId: text(row.run_id, 'gap.run_id'), kind: enumeration(row.kind, ['UNKNOWN', 'MISSING', 'UNAVAILABLE', 'CONFLICTED'] as const, 'gap.kind'), field: text(row.field, 'gap.field'), domain: text(row.domain, 'gap.domain'), reason: text(row.reason, 'gap.reason'), provider: nullableText(row.provider, 'gap.provider'), observedAt: instant(row.observed_at, 'gap.observed_at'), createdAt: instant(row.created_at, 'gap.created_at') }
      }),
      decisionDiff: { id: text(diff.id, 'diff.id'), decisionId: text(diff.decision_id, 'diff.decision_id'), previousDecisionId: nullableText(diff.previous_decision_id, 'diff.previous_decision_id'), generator: enumeration(diff.generator, ['DETERMINISTIC_CODE'] as const, 'diff.generator'), changes: record(diff.changes, 'diff.changes'), createdAt: instant(diff.created_at, 'diff.created_at') },
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

export async function getHistoricalBars(
  options: LiveDataClientOptions,
  symbol: string,
  start: string,
  end: string,
): Promise<{ decisionTime: string; items: MarketBar[]; status: LiveDataStatus }> {
  if (!symbolPattern.test(symbol)) throw new LiveDataApiError('contract', 'Bar symbol is invalid')
  const query = new URLSearchParams({
    decision_time: instant(options.decisionTime, 'bars.decision_time'),
    end: instant(end, 'bars.end'),
    limit: '45',
    start: instant(start, 'bars.start'),
    timeframe: '1Day',
  })
  const value = await requestJson(options, `/api/v1/market-data/bars/${symbol}?${query}`)
  return contract(() => {
    const source = record(value, 'bars')
    if (!Array.isArray(source.items)) throw new TypeError('bars.items must be an array')
    return {
      decisionTime: instant(source.decision_time, 'bars.decision_time'),
      items: source.items.map((item, index) => {
        const row = record(item, `bars.items[${index}]`)
        const rowSymbol = text(row.symbol, 'bar.symbol')
        if (rowSymbol !== symbol) throw new TypeError('bar.symbol does not match the requested symbol')
        return {
          availableAt: instant(row.available_at, 'bar.available_at'),
          close: decimal(row.close, 'bar.close'),
          conflict: booleanValue(row.conflict, 'bar.conflict'),
          contentHash: text(row.content_hash, 'bar.content_hash'),
          coverage: enumeration(row.coverage, ['IEX', 'SIP'] as const, 'bar.coverage'),
          eventTime: instant(row.event_time, 'bar.event_time'),
          feedType: text(row.feed_type, 'bar.feed_type'),
          high: decimal(row.high, 'bar.high'),
          ingestedAt: instant(row.ingested_at, 'bar.ingested_at'),
          low: decimal(row.low, 'bar.low'),
          open: decimal(row.open, 'bar.open'),
          provider: text(row.provider, 'bar.provider'),
          rawObjectKey: text(row.raw_object_key, 'bar.raw_object_key'),
          session: enumeration(row.session, ['PRE_MARKET', 'REGULAR', 'AFTER_HOURS', 'OVERNIGHT'] as const, 'bar.session'),
          symbol: rowSymbol,
          timeframe: enumeration(row.timeframe, ['1Min', '1Day'] as const, 'bar.timeframe'),
          volume: decimal(row.volume, 'bar.volume'),
        }
      }),
      status: enumeration(source.status, ['SUCCESS', 'DEGRADED', 'FAILURE'] as const, 'bars.status'),
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
        configured: booleanValue(row.configured, `${name}.configured`),
        mode: enumeration(row.mode, ['fixture', 'read_only', 'unavailable'] as const, `${name}.mode`),
        operatorAction: row.operator_action === undefined || row.operator_action === null
          ? null
          : text(row.operator_action, `${name}.operator_action`),
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
    const nullableText = (value: unknown, path: string) => value === null ? null : text(value, path)
    const nullableDecimal = (value: unknown, path: string) => value === null ? null : decimal(value, path)
    const nullableInstant = (value: unknown, path: string) => value === null ? null : instant(value, path)
    const nav = (value: JsonRecord, path: string): PortfolioNav => ({
      availableAt: instant(value.available_at, `${path}.available_at`),
      eventTime: instant(value.event_time, `${path}.event_time`),
      id: text(value.id, `${path}.id`),
      nav: decimal(value.nav, `${path}.nav`),
      portfolioId: text(value.portfolio_id, `${path}.portfolio_id`),
    })
    const positions = records('positions').map((value, index) => {
      const path = `portfolio.positions[${index}]`
      return {
        averageCost: decimal(value.average_cost, `${path}.average_cost`),
        marketPrice: nullableDecimal(value.market_price, `${path}.market_price`),
        marketValue: nullableDecimal(value.market_value, `${path}.market_value`),
        priceAvailableAt: nullableInstant(value.price_available_at, `${path}.price_available_at`),
        quantity: decimal(value.quantity, `${path}.quantity`),
        symbol: text(value.symbol, `${path}.symbol`),
        unrealizedPnl: nullableDecimal(value.unrealized_pnl, `${path}.unrealized_pnl`),
      }
    })
    const riskDecisions = records('risk_decisions').map((value, index) => {
      const path = `portfolio.risk_decisions[${index}]`
      const reasonCodes = value.reason_codes
      if (!Array.isArray(reasonCodes)) throw new TypeError(`${path}.reason_codes must be an array`)
      return {
        approvedDelta: decimal(value.approved_delta, `${path}.approved_delta`),
        approvedWeight: decimal(value.approved_weight, `${path}.approved_weight`),
        authorizationSource: text(value.authorization_source, `${path}.authorization_source`),
        authorizedSide: value.authorized_side === null ? null : enumeration(value.authorized_side, ['BUY', 'SELL'] as const, `${path}.authorized_side`),
        createdAt: instant(value.created_at, `${path}.created_at`),
        currentWeight: decimal(value.current_weight, `${path}.current_weight`),
        decidedAt: instant(value.decided_at, `${path}.decided_at`),
        id: text(value.id, `${path}.id`),
        marketContextSnapshotId: nullableText(value.market_context_snapshot_id, `${path}.market_context_snapshot_id`),
        maxOrderQuantity: decimal(value.max_order_quantity, `${path}.max_order_quantity`),
        portfolioId: text(value.portfolio_id, `${path}.portfolio_id`),
        proposalId: text(value.proposal_id, `${path}.proposal_id`),
        reasonCodes: reasonCodes.map((reason, reasonIndex) => text(reason, `${path}.reason_codes[${reasonIndex}]`)),
        referenceNav: nullableDecimal(value.reference_nav, `${path}.reference_nav`),
        referencePrice: nullableDecimal(value.reference_price, `${path}.reference_price`),
        researchDecisionId: nullableText(value.research_decision_id, `${path}.research_decision_id`),
        requestedWeight: decimal(value.requested_weight, `${path}.requested_weight`),
        riskPolicyVersionId: text(value.risk_policy_version_id, `${path}.risk_policy_version_id`),
        status: enumeration(value.status, ['APPROVED', 'CLIPPED', 'REJECTED'] as const, `${path}.status`),
        symbol: text(value.symbol, `${path}.symbol`),
      }
    })
    const fills = records('fills').map((value, index) => {
      const path = `portfolio.fills[${index}]`
      return {
        createdAt: instant(value.created_at, `${path}.created_at`),
        currency: enumeration(value.currency, ['USD'] as const, `${path}.currency`),
        executionPolicyVersionId: text(value.execution_policy_version_id, `${path}.execution_policy_version_id`),
        fee: decimal(value.fee, `${path}.fee`),
        filledAt: instant(value.filled_at, `${path}.filled_at`),
        id: text(value.id, `${path}.id`),
        idempotencyKey: text(value.idempotency_key, `${path}.idempotency_key`),
        orderId: text(value.order_id, `${path}.order_id`),
        portfolioId: text(value.portfolio_id, `${path}.portfolio_id`),
        price: decimal(value.price, `${path}.price`),
        quantity: decimal(value.quantity, `${path}.quantity`),
        reversalOfId: nullableText(value.reversal_of_id, `${path}.reversal_of_id`),
        side: enumeration(value.side, ['BUY', 'SELL'] as const, `${path}.side`),
        sourceBarTime: instant(value.source_bar_time, `${path}.source_bar_time`),
        symbol: text(value.symbol, `${path}.symbol`),
      }
    })
    const cashLedger = records('cash_ledger').map((value, index) => {
      const path = `portfolio.cash_ledger[${index}]`
      return {
        account: text(value.account, `${path}.account`),
        createdAt: instant(value.created_at, `${path}.created_at`),
        credit: decimal(value.credit, `${path}.credit`),
        currency: enumeration(value.currency, ['USD'] as const, `${path}.currency`),
        debit: decimal(value.debit, `${path}.debit`),
        id: text(value.id, `${path}.id`),
        idempotencyKey: text(value.idempotency_key, `${path}.idempotency_key`),
        occurredAt: instant(value.occurred_at, `${path}.occurred_at`),
        reversalOfId: nullableText(value.reversal_of_id, `${path}.reversal_of_id`),
        sourceId: text(value.source_id, `${path}.source_id`),
        transactionId: text(value.transaction_id, `${path}.transaction_id`),
      }
    })
    const performanceHistory = records('performance_history').map((value, index) => nav(value, `portfolio.performance_history[${index}]`))
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
      latestNav: latest ? nav(latest, 'portfolio.latest_nav') : null,
      positions,
      riskDecisions,
      orders: records('orders'),
      fills,
      cashLedger,
      performanceHistory,
    }
  })
}

export async function getStockResearch(
  options: LiveDataClientOptions,
  symbol: string,
): Promise<StockResearch> {
  if (!symbolPattern.test(symbol)) throw new LiveDataApiError('contract', 'Research symbol is invalid')
  const query = new URLSearchParams({ decision_time: options.decisionTime })
  const value = await requestJson(options, `/api/v1/stocks/${encodeURIComponent(symbol)}/research?${query}`)
  return contract(() => {
    const page = record(value, 'research')
    if (!Array.isArray(page.items)) throw new TypeError('research.items must be an array')
    const records = page.items.map((item, index) => {
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
    if (!Array.isArray(page.sec_filings)) throw new TypeError('research.sec_filings must be an array')
    if (!Array.isArray(page.financial_facts)) throw new TypeError('research.financial_facts must be an array')
    const secFilings = page.sec_filings.map((item, index) => {
      const row = record(item, `sec_filings[${index}]`)
      return {
        acceptedAt: instant(row.accepted_at, 'filing.accepted_at'), accessionNumber: text(row.accession_number, 'filing.accession_number'),
        availableAt: instant(row.available_at, 'filing.available_at'), description: text(row.description, 'filing.description'),
        contentHash: text(row.content_hash, 'filing.content_hash'), eventTime: instant(row.event_time, 'filing.event_time'),
        documentRawObjectKey: text(row.document_raw_object_key, 'filing.document_raw_object_key'),
        filingDate: text(row.filing_date, 'filing.filing_date'), form: text(row.form, 'filing.form'),
        id: text(row.id, 'filing.id'), provider: text(row.provider, 'filing.provider'),
        rawObjectKey: text(row.raw_object_key, 'filing.raw_object_key'),
        reportDate: row.report_date === null ? null : text(row.report_date, 'filing.report_date'),
      }
    })
    const financialFacts = page.financial_facts.map((item, index) => {
      const row = record(item, `financial_facts[${index}]`)
      return {
        accessionNumber: text(row.accession_number, 'fact.accession_number'), availableAt: instant(row.available_at, 'fact.available_at'),
        canonicalConcept: row.canonical_concept === null ? null : text(row.canonical_concept, 'fact.canonical_concept'),
        contentHash: text(row.content_hash, 'fact.content_hash'), eventTime: instant(row.event_time, 'fact.event_time'),
        currency: row.currency === null ? null : text(row.currency, 'fact.currency'), id: text(row.id, 'fact.id'),
        mappingStatus: enumeration(row.mapping_status, ['EXACT', 'DERIVED', 'UNMAPPED', 'AMBIGUOUS'] as const, 'fact.mapping_status'),
        periodEnd: text(row.period_end, 'fact.period_end'), periodStart: text(row.period_start, 'fact.period_start'),
        provider: text(row.provider, 'fact.provider'), sourceConcept: text(row.source_concept, 'fact.source_concept'),
        rawObjectKey: text(row.raw_object_key, 'fact.raw_object_key'),
        taxonomy: text(row.taxonomy, 'fact.taxonomy'), unit: text(row.unit, 'fact.unit'), value: decimal(row.value, 'fact.value'),
      }
    })
    if (!Array.isArray(page.news_articles)) throw new TypeError('research.news_articles must be an array')
    if (!Array.isArray(page.earnings_events)) throw new TypeError('research.earnings_events must be an array')
    if (!Array.isArray(page.option_snapshots)) throw new TypeError('research.option_snapshots must be an array')
    if (!Array.isArray(page.unavailable_domains)) throw new TypeError('research.unavailable_domains must be an array')
    const newsArticles = page.news_articles.map((item, index) => {
      const row = record(item, `news_articles[${index}]`)
      return {
        availableAt: instant(row.available_at, 'news.available_at'), contentHash: text(row.content_hash, 'news.content_hash'),
        eventTime: instant(row.event_time, 'news.event_time'), headline: text(row.headline, 'news.headline'),
        id: text(row.id, 'news.id'), provider: text(row.provider, 'news.provider'), rawObjectKey: text(row.raw_object_key, 'news.raw_object_key'),
        source: text(row.source, 'news.source'), summary: text(row.summary, 'news.summary'),
      }
    })
    const earningsEvents = page.earnings_events.map((item, index) => {
      const row = record(item, `earnings_events[${index}]`)
      return {
        availableAt: instant(row.available_at, 'earnings.available_at'), contentHash: text(row.content_hash, 'earnings.content_hash'),
        currency: row.currency === null ? null : text(row.currency, 'earnings.currency'),
        estimate: row.estimate === null ? null : decimal(row.estimate, 'earnings.estimate'),
        eventDate: text(row.event_date, 'earnings.event_date'), eventTime: instant(row.event_time, 'earnings.event_time'),
        fiscalDateEnd: text(row.fiscal_date_end, 'earnings.fiscal_date_end'), id: text(row.id, 'earnings.id'),
        provider: text(row.provider, 'earnings.provider'), rawObjectKey: text(row.raw_object_key, 'earnings.raw_object_key'),
      }
    })
    const optionSnapshots = page.option_snapshots.map((item, index) => {
      const row = record(item, `option_snapshots[${index}]`)
      return {
        availableAt: instant(row.available_at, 'options.available_at'), contentHash: text(row.content_hash, 'options.content_hash'),
        eventTime: instant(row.event_time, 'options.event_time'), feedType: text(row.feed_type, 'options.feed_type'),
        id: text(row.id, 'options.id'), payload: record(row.payload, 'options.payload'), provider: text(row.provider, 'options.provider'),
        rawObjectKey: text(row.raw_object_key, 'options.raw_object_key'),
      }
    })
    const unavailableDomains = page.unavailable_domains.map((item, index) => enumeration(
      item, ['EARNINGS', 'NEWS', 'OPTIONS', 'ANALYST_TARGETS'] as const, `research.unavailable_domains[${index}]`,
    ))
    const reasonRows = record(page.unavailable_reasons, 'research.unavailable_reasons')
    const unavailableReasons: StockResearch['unavailableReasons'] = {}
    for (const domain of unavailableDomains) {
      unavailableReasons[domain] = text(
        reasonRows[domain],
        `research.unavailable_reasons.${domain}`,
      )
    }
    return {
      earningsEvents,
      financialFacts,
      newsArticles,
      optionSnapshots,
      records,
      secFilings,
      unavailableDomains,
      unavailableReasons,
    }
  })
}

export async function getDataQuality(
  options: LiveDataClientOptions,
  provider: string,
  dataset: string,
): Promise<DataQuality[]> {
  if (!provider.trim() || !dataset.trim()) throw new LiveDataApiError('contract', 'Data quality scope is required')
  const query = new URLSearchParams({
    dataset,
    decision_time: options.decisionTime,
    provider,
  })
  const value = await requestJson(options, `/api/v1/data-quality?${query}`)
  return contract(() => {
    const page = record(value, 'data_quality')
    enumeration(page.status, ['SUCCESS', 'DEGRADED', 'FAILURE'] as const, 'data_quality.status')
    if (!Array.isArray(page.items)) throw new TypeError('data_quality.items must be an array')
    const parsed = page.items.map((item, index) => {
      const row = record(item, `data_quality[${index}]`)
      return {
        conflict: booleanValue(row.conflict, 'data_quality.conflict'),
        coverage: row.coverage === null ? null : enumeration(row.coverage, ['IEX', 'SIP'] as const, 'data_quality.coverage'),
        dataset: text(row.dataset, 'data_quality.dataset'),
        delay: row.delay === null ? null : text(row.delay, 'data_quality.delay'),
        dimension: text(row.dimension, 'data_quality.dimension'),
        freshness: row.freshness === null ? null : text(row.freshness, 'data_quality.freshness'),
        id: text(row.id, 'data_quality.id'),
        observedAt: instant(row.observed_at, 'data_quality.observed_at'),
        provider: text(row.provider, 'data_quality.provider'),
        status: enumeration(row.status, ['PASS', 'DEGRADED', 'UNAVAILABLE', 'FAIL'] as const, 'data_quality.status'),
      }
    })
    const latest = new Map<string, DataQuality>()
    for (const item of parsed) {
      const key = `${item.provider}:${item.dataset}:${item.dimension}`
      if (!latest.has(key)) latest.set(key, item)
    }
    return [...latest.values()]
  })
}
