import type { DataQuality, PortfolioAction, ResearchOpinion } from './api'

export type WatchlistSnapshot = {
  asOf: string
  limit: number
  symbols: Array<{
    dailyReturn: string
    dataQuality: DataQuality
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
  dayReturn: string
  drawdown: string
  execution: { fillTiming: string; ledgerStatus: string; policyVersion: string }
  nav: string
  positions: Array<{ action: PortfolioAction; marketValue: string; quantity: string; symbol: string; weight: string }>
}

export type AlertsSnapshot = {
  alerts: Array<{
    acknowledged: boolean
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
  lesson: { id: string; proposal: string; status: 'PENDING' | 'APPROVED' | 'REJECTED' }
  outcomes: Array<{ horizon: string; return: string; symbol: string }>
  replay: { availableAtCutoff: string; result: string; scoreDelta: string }
}

export type EvalAdminSnapshot = {
  asOf: string
  policyVersions: Array<{ active: boolean; kind: string; version: string }>
}
