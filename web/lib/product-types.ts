import type { DataQuality, PortfolioAction, ResearchOpinion } from './api'

export type WatchlistSnapshot = {
  asOf: string
  limit: number
  symbols: Array<{
    dailyReturn: string
    dataQuality: DataQuality
    dailyResearch: boolean
    intradayMonitoring: boolean
    alertThreshold: string
    nextEarningsAt: string | null
    lastResearchAt: string
    portfolioAction: PortfolioAction
    price: string
    researchOpinion: ResearchOpinion
    symbol: string
  }>
}

export type ResearchSnapshot = {
  asOf: string
  decisionDiff: Array<{ field: string; from: string; to: string }>
  fundamentals: Array<{ label: string; source: string; value: string }>
  earnings: Array<{ period: string; reportedAt: string; summary: string }>
  news: Array<{ eventTime: string; headline: string; provider: string }>
  options: { status: 'AVAILABLE' | 'UNAVAILABLE'; summary: string }
  analystTargets: { asOf: string; consensus: string; provider: string; targetPrice: string }
  decisionHistory: Array<{
    asOf: string
    confidence: string
    id: string
    portfolioAction: PortfolioAction
    researchOpinion: ResearchOpinion
  }>
  gaps: Array<{ domain: string; kind: 'UNKNOWN' | 'MISSING' | 'UNAVAILABLE' | 'CONFLICTED'; reason: string }>
  invalidationConditions: string[]
  lineage: Array<{
    claim: { id: string; statement: string }
    evidence: {
      availableAt: string
      dataQuality: DataQuality
      id: string
      provider: string
      relation: 'SUPPORTS' | 'CONTRADICTS' | 'CONTEXT'
      summary: string
    }
    toolCall: { id: string; name: string }
  }>
  policyPins: Array<{ label: string; version: string }>
  portfolioAction: PortfolioAction
  researchOpinion: ResearchOpinion
  symbol: string
  thesis: {
    confidence: string
    direction: string
    horizon: string
    summary: string
  }
}

export type RunTraceSnapshot = {
  asOf: string
  budgets: {
    costUsd: string
    llmCalls: { limit: number; used: number }
    tokens: number
    toolCalls: { limit: number; used: number }
  }
  events: Array<{
    detail: string
    durationMs: string
    eventTime: string
    id: string
    sequence: number
    status: 'COMPLETED' | 'RUNNING' | 'RETRYING' | 'FALLBACK'
    type: string
  }>
  lastEventId: string
  runId: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  symbol: string
}

export type PortfolioSnapshot = {
  asOf: string
  benchmarks: Array<{ label: string; return: string }>
  currency: 'USD'
  cash: string
  cashLedger: Array<{ amount: string; balance: string; eventTime: string; id: string; kind: string }>
  dayReturn: string
  drawdown: string
  execution: { fillTiming: string; ledgerStatus: string; policyVersion: string }
  nav: string
  performanceHistory: Array<{
    cumulativeReturn: string
    dailyReturn: string
    drawdown: string
    nav: string
    time: string
  }>
  positions: Array<{ action: PortfolioAction; marketValue: string; quantity: string; symbol: string; unrealizedPnl: string; weight: string }>
  riskDecisions: Array<{ id: string; orderIntentId: string; reason: string; status: 'ACCEPTED' | 'REJECTED' }>
  fills: Array<{ eventTime: string; id: string; orderId: string; price: string; quantity: string; symbol: string }>
}

export type AlertCategory = 'PRICE' | 'VOLUME' | 'OPTIONS' | 'EARNINGS' | 'NEWS' | 'ANALYST_TARGET' | 'PORTFOLIO_RISK'

export type AlertsSnapshot = {
  alerts: Array<{
    acknowledged: boolean
    category: AlertCategory
    eventTime: string
    evidenceId: string
    explanation: { detail: string; status: 'COMPLETED' | 'FAILED' | 'TIMEOUT' | 'DISABLED' }
    id: string
    materiality: string
    reviewAction: string
    severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
    summary: string
    symbol: string
    thesisId: string
  }>
  asOf: string
}

export type WeeklyReviewSnapshot = {
  asOf: string
  attribution: Array<{ category: string; detail: string }>
  calibration: Array<{ bucket: string; decisionCount: number; observedHitRate: string }>
  lesson: { id: string; proposal: string; status: 'PENDING' | 'APPROVED' | 'REJECTED' }
  outcomes: Array<{ confidence: string; horizon: string; return: string; symbol: string; thesisHit: 'HIT' | 'MISS' | 'INCONCLUSIVE' }>
  replay: { availableAtCutoff: string; result: string; scoreDelta: string }
}

export type EvalAdminSnapshot = {
  asOf: string
  policyVersions: Array<{ active: boolean; kind: string; version: string }>
}
