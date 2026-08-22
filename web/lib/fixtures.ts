import type {
  AlertsSnapshot,
  EvalAdminSnapshot,
  PortfolioSnapshot,
  ResearchSnapshot,
  RunTraceSnapshot,
  WatchlistSnapshot,
  WeeklyReviewSnapshot,
} from './product-types'

const freshQuality = {
  conflict: false,
  coverage: '0.94',
  delaySeconds: '0',
  freshness: 'FRESH' as const,
  provider: 'fixture-market',
}

export const fixtureWatchlistSnapshot: WatchlistSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  limit: 20,
  symbols: [
    { symbol: 'NVDA', price: '129.84', dailyReturn: '0.0214', researchOpinion: 'BULLISH', portfolioAction: 'HOLD', lastResearchAt: '2026-08-21T20:00:00Z', dataQuality: freshQuality },
    { symbol: 'MSFT', price: '507.24', dailyReturn: '-0.0036', researchOpinion: 'NEUTRAL', portfolioAction: 'NO_ACTION', lastResearchAt: '2026-08-21T20:00:00Z', dataQuality: { ...freshQuality, conflict: true, coverage: '0.71', delaySeconds: '900', freshness: 'STALE' } },
    { symbol: 'AAPL', price: '226.41', dailyReturn: '0.0061', researchOpinion: 'NEUTRAL', portfolioAction: 'HOLD', lastResearchAt: '2026-08-21T20:00:00Z', dataQuality: { ...freshQuality, coverage: '0.88' } },
    { symbol: 'AMD', price: '168.05', dailyReturn: '-0.0128', researchOpinion: 'BEARISH', portfolioAction: 'REDUCE', lastResearchAt: '2026-08-21T20:00:00Z', dataQuality: { ...freshQuality, coverage: '0.83' } },
    { symbol: 'TSLA', price: '320.11', dailyReturn: '0.0042', researchOpinion: 'ABSTAIN', portfolioAction: 'NO_ACTION', lastResearchAt: '2026-08-21T20:00:00Z', dataQuality: { ...freshQuality, conflict: true, coverage: '0.52', freshness: 'STALE', provider: 'fixture-conflicted' } },
  ],
}

export const fixtureResearchSnapshot: ResearchSnapshot = {
  symbol: 'NVDA',
  asOf: '2026-08-21T20:00:00Z',
  researchOpinion: 'BULLISH',
  portfolioAction: 'HOLD',
  thesis: {
    direction: 'Constructive, evidence-bounded',
    summary: 'Demand remains resilient in the frozen fixture, while supply visibility and valuation limit conviction.',
    confidence: '0.74',
    horizon: '6–12 months',
  },
  invalidationConditions: [
    'Data-center revenue growth falls below the frozen policy threshold.',
    'Confirmed supply constraints persist across two decision cutoffs.',
  ],
  gaps: [
    { kind: 'UNAVAILABLE', domain: 'options', reason: 'Options fixture did not cover the full decision window.' },
    { kind: 'CONFLICTED', domain: 'supply', reason: 'Two normalized fixture records disagree on lead-time direction.' },
  ],
  lineage: [
    {
      claim: { id: 'claim-nvda-demand', statement: 'Data-center demand remained resilient at the frozen cutoff.' },
      evidence: {
        id: 'evidence-sec-revenue',
        relation: 'SUPPORTS',
        summary: 'Normalized filing facts support the demand claim.',
        provider: 'SEC Company Facts',
        availableAt: '2026-08-21T18:30:00Z',
        dataQuality: freshQuality,
      },
      toolCall: { id: 'tool-sec-companyfacts', name: 'sec.company_facts' },
    },
    {
      claim: { id: 'claim-nvda-supply', statement: 'Supply visibility is improving.' },
      evidence: {
        id: 'evidence-supply-conflict',
        relation: 'CONTRADICTS',
        summary: 'A conflicting fixture record reports unchanged lead times.',
        provider: 'Fixture Market Research',
        availableAt: '2026-08-21T19:10:00Z',
        dataQuality: { ...freshQuality, conflict: true, coverage: '0.63', provider: 'fixture-research' },
      },
      toolCall: { id: 'tool-market-search', name: 'market.search' },
    },
  ],
  decisionDiff: [
    { field: 'confidence', from: '0.69', to: '0.74' },
    { field: 'invalidation_conditions', from: '1 condition', to: '2 conditions' },
  ],
  policyPins: [
    { label: 'Research scoring', version: 'research-scoring-v1' },
    { label: 'Risk', version: 'risk-v1' },
    { label: 'Execution', version: 'execution-v1' },
    { label: 'Confidence', version: 'confidence-v1' },
    { label: 'Prompt', version: 'research-prompt-v1' },
    { label: 'Model', version: 'fixture-proposer-v1' },
  ],
}

export const fixtureRunTrace: RunTraceSnapshot = {
  runId: 'b1000000-0000-4000-8000-000000000001',
  symbol: 'NVDA',
  status: 'RUNNING',
  asOf: '2026-08-21T20:00:00Z',
  lastEventId: 'event-0007',
  budgets: {
    llmCalls: { used: 6, limit: 10 },
    toolCalls: { used: 9, limit: 16 },
    tokens: 12480,
    costUsd: '0.84',
  },
  events: [
    { id: 'event-0001', sequence: 1, type: 'run.started', status: 'COMPLETED', detail: 'Pinned policies, prompt, model, and data cutoff.', eventTime: '2026-08-21T20:00:01Z' },
    { id: 'event-0002', sequence: 2, type: 'node.completed', status: 'COMPLETED', detail: 'Preflight completed', eventTime: '2026-08-21T20:00:03Z' },
    { id: 'event-0003', sequence: 3, type: 'tool.completed', status: 'RETRYING', detail: 'SEC tool retry 1 of 3', eventTime: '2026-08-21T20:00:08Z' },
    { id: 'event-0004', sequence: 4, type: 'tool.completed', status: 'FALLBACK', detail: 'Options provider unavailable · fixture fallback retained an explicit gap', eventTime: '2026-08-21T20:00:12Z' },
    { id: 'event-0005', sequence: 5, type: 'checkpoint.saved', status: 'COMPLETED', detail: 'Checkpoint saved after evidence judgment', eventTime: '2026-08-21T20:00:18Z' },
    { id: 'event-0006', sequence: 6, type: 'node.completed', status: 'COMPLETED', detail: 'Deterministic score and confidence completed', eventTime: '2026-08-21T20:00:24Z' },
    { id: 'event-0007', sequence: 7, type: 'node.started', status: 'RUNNING', detail: 'Citation verifier running', eventTime: '2026-08-21T20:00:29Z' },
  ],
}

export const fixturePortfolioSnapshot: PortfolioSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  nav: '100425.18',
  currency: 'USD',
  dayReturn: '0.0042',
  drawdown: '-0.0180',
  benchmarks: [
    { label: 'Cash', return: '0' },
    { label: 'QQQ', return: '0.0038' },
    { label: 'Equal weight', return: '0.0031' },
    { label: 'Momentum', return: '0.0045' },
  ],
  positions: [
    { symbol: 'NVDA', quantity: '120', marketValue: '15580.80', weight: '0.1551', action: 'HOLD' },
    { symbol: 'MSFT', quantity: '20', marketValue: '10144.80', weight: '0.1010', action: 'NO_ACTION' },
  ],
  execution: {
    fillTiming: 'Next eligible bar after decision time',
    policyVersion: 'execution-v1',
    ledgerStatus: 'Balanced ledger · immutable fill and cash facts',
  },
}

export const fixtureAlertsSnapshot: AlertsSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  alerts: [
    {
      id: 'alert-nvda-volume-001',
      symbol: 'NVDA',
      severity: 'HIGH',
      materiality: '0.82',
      summary: 'Relative volume and return z-score crossed the frozen deterministic rule.',
      reviewAction: 'Review thesis invalidation conditions',
      eventTime: '2026-08-21T19:45:00Z',
      thesisId: 'thesis-nvda-v3',
      evidenceId: 'evidence-volume-breakout',
      acknowledged: false,
      explanation: { status: 'FAILED', detail: 'Explanation unavailable; deterministic alert remains valid and visible.' },
    },
  ],
}

export const fixtureWeeklyReviewSnapshot: WeeklyReviewSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  outcomes: [
    { symbol: 'NVDA', horizon: '5 day', return: '0.031' },
    { symbol: 'MSFT', horizon: '5 day', return: '-0.006' },
  ],
  attribution: [
    { category: 'Timing error', detail: 'Correct direction, but entry followed the strongest move in the frozen replay.' },
    { category: 'Evidence gap', detail: 'Options coverage was unavailable at the historical cutoff.' },
  ],
  lesson: {
    id: 'lesson-risk-regime-001',
    proposal: 'Require a second regime confirmation before increasing exposure after a large gap.',
    status: 'PENDING',
  },
  replay: {
    availableAtCutoff: '2026-08-15T20:00:00Z',
    result: 'Point-in-time replay completed with only historically available facts.',
    scoreDelta: '0.07',
  },
}

export const fixtureEvalAdminSnapshot: EvalAdminSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  policyVersions: [
    { kind: 'Research scoring', version: 'research-scoring-v1', active: true },
    { kind: 'Risk', version: 'risk-v1', active: true },
    { kind: 'Execution', version: 'execution-v1', active: true },
    { kind: 'Confidence', version: 'confidence-v1', active: true },
  ],
}

export function getFixtureResearchSnapshot(symbol: string): ResearchSnapshot | null {
  return symbol.toUpperCase() === fixtureResearchSnapshot.symbol ? fixtureResearchSnapshot : null
}

export function getFixtureRunTrace(runId: string): RunTraceSnapshot | null {
  return runId === 'latest' || runId === fixtureRunTrace.runId ? fixtureRunTrace : null
}
