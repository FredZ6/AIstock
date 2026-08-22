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
    { symbol: 'NVDA', price: '129.84', dailyReturn: '0.0214', researchOpinion: 'BULLISH', portfolioAction: 'HOLD', lastResearchAt: '2026-08-21T20:00:00Z', dailyResearch: true, intradayMonitoring: true, alertThreshold: '0.025', nextEarningsAt: '2026-08-27T20:00:00Z', dataQuality: freshQuality },
    { symbol: 'MSFT', price: '507.24', dailyReturn: '-0.0036', researchOpinion: 'NEUTRAL', portfolioAction: 'NO_ACTION', lastResearchAt: '2026-08-21T20:00:00Z', dailyResearch: true, intradayMonitoring: false, alertThreshold: '0.030', nextEarningsAt: null, dataQuality: { ...freshQuality, conflict: true, coverage: '0.71', delaySeconds: '900', freshness: 'STALE' } },
    { symbol: 'AAPL', price: '226.41', dailyReturn: '0.0061', researchOpinion: 'NEUTRAL', portfolioAction: 'HOLD', lastResearchAt: '2026-08-21T20:00:00Z', dailyResearch: true, intradayMonitoring: false, alertThreshold: '0.025', nextEarningsAt: null, dataQuality: { ...freshQuality, coverage: '0.88' } },
    { symbol: 'AMD', price: '168.05', dailyReturn: '-0.0128', researchOpinion: 'BEARISH', portfolioAction: 'REDUCE', lastResearchAt: '2026-08-21T20:00:00Z', dailyResearch: false, intradayMonitoring: true, alertThreshold: '0.040', nextEarningsAt: null, dataQuality: { ...freshQuality, coverage: '0.83' } },
    { symbol: 'TSLA', price: '320.11', dailyReturn: '0.0042', researchOpinion: 'ABSTAIN', portfolioAction: 'NO_ACTION', lastResearchAt: '2026-08-21T20:00:00Z', dailyResearch: false, intradayMonitoring: false, alertThreshold: '0.050', nextEarningsAt: null, dataQuality: { ...freshQuality, conflict: true, coverage: '0.52', freshness: 'STALE', provider: 'fixture-conflicted' } },
  ],
}

export const fixtureResearchSnapshot: ResearchSnapshot = {
  symbol: 'NVDA',
  asOf: '2026-08-21T20:00:00Z',
  report: { id: 'report-nvda-v3', generatedAt: '2026-08-21T20:00:30Z' },
  researchOpinion: 'BULLISH',
  portfolioAction: 'HOLD',
  fundamentals: [
    { label: 'Revenue trend', value: 'Expanding in frozen fixture', source: 'SEC fixture' },
    { label: 'Gross margin', value: 'Stable in frozen fixture', source: 'SEC fixture' },
  ],
  earnings: [{ period: 'Latest frozen filing', reportedAt: '2026-08-20T20:00:00Z', summary: 'Available before the decision cutoff.' }],
  news: [{ eventTime: '2026-08-21T17:00:00Z', headline: 'Frozen fixture supply update', provider: 'Fixture Market Research' }],
  options: { status: 'UNAVAILABLE', summary: 'The frozen fixture does not cover the full options window.' },
  analystTargets: { asOf: '2026-08-21T18:00:00Z', consensus: 'Unavailable', targetPrice: 'Unavailable', provider: 'Fixture analyst feed' },
  decisionHistory: [
    { id: 'decision-nvda-v3', asOf: '2026-08-21T20:00:00Z', researchOpinion: 'BULLISH', portfolioAction: 'HOLD', confidence: '0.74' },
    { id: 'decision-nvda-v2', asOf: '2026-08-15T20:00:00Z', researchOpinion: 'NEUTRAL', portfolioAction: 'NO_ACTION', confidence: '0.69' },
  ],
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
    { id: 'event-0001', sequence: 1, type: 'run.started', status: 'COMPLETED', detail: 'Pinned policies, prompt, model, and data cutoff.', durationMs: '0', eventTime: '2026-08-21T20:00:01Z' },
    { id: 'event-0002', sequence: 2, type: 'node.completed', status: 'COMPLETED', detail: 'Preflight completed', durationMs: '2000', eventTime: '2026-08-21T20:00:03Z' },
    { id: 'event-0003', sequence: 3, type: 'tool.completed', status: 'RETRYING', detail: 'SEC tool retry 1 of 3', durationMs: '5000', eventTime: '2026-08-21T20:00:08Z' },
    { id: 'event-0004', sequence: 4, type: 'tool.completed', status: 'FALLBACK', detail: 'Options provider unavailable · fixture fallback retained an explicit gap', durationMs: '4000', eventTime: '2026-08-21T20:00:12Z' },
    { id: 'event-0005', sequence: 5, type: 'checkpoint.saved', status: 'COMPLETED', detail: 'Checkpoint saved after evidence judgment', durationMs: '6000', eventTime: '2026-08-21T20:00:18Z' },
    { id: 'event-0006', sequence: 6, type: 'node.completed', status: 'COMPLETED', detail: 'Deterministic score and confidence completed', durationMs: '6000', eventTime: '2026-08-21T20:00:24Z' },
    { id: 'event-0007', sequence: 7, type: 'node.started', status: 'RUNNING', detail: 'Citation verifier running', durationMs: '5000', eventTime: '2026-08-21T20:00:29Z' },
  ],
}

export const fixturePortfolioSnapshot: PortfolioSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  nav: '100425.18',
  cash: '74699.58',
  currency: 'USD',
  dayReturn: '0.0042',
  drawdown: '-0.0180',
  performanceHistory: [
    { time: '2026-05-23T20:00:00Z', nav: '100000.00', dailyReturn: '0', cumulativeReturn: '0', drawdown: '0' },
    { time: '2026-05-30T20:00:00Z', nav: '100180.00', dailyReturn: '0.0018', cumulativeReturn: '0.0018', drawdown: '0' },
    { time: '2026-06-06T20:00:00Z', nav: '99840.00', dailyReturn: '-0.0034', cumulativeReturn: '-0.0016', drawdown: '-0.0034' },
    { time: '2026-06-13T20:00:00Z', nav: '100520.00', dailyReturn: '0.0068', cumulativeReturn: '0.0052', drawdown: '0' },
    { time: '2026-06-20T20:00:00Z', nav: '101040.00', dailyReturn: '0.0052', cumulativeReturn: '0.0104', drawdown: '0' },
    { time: '2026-06-27T20:00:00Z', nav: '100610.00', dailyReturn: '-0.0043', cumulativeReturn: '0.0061', drawdown: '-0.0043' },
    { time: '2026-07-04T20:00:00Z', nav: '101380.00', dailyReturn: '0.0077', cumulativeReturn: '0.0138', drawdown: '0' },
    { time: '2026-07-11T20:00:00Z', nav: '101760.00', dailyReturn: '0.0037', cumulativeReturn: '0.0176', drawdown: '0' },
    { time: '2026-07-18T20:00:00Z', nav: '100920.00', dailyReturn: '-0.0083', cumulativeReturn: '0.0092', drawdown: '-0.0083' },
    { time: '2026-07-25T20:00:00Z', nav: '102265.97', dailyReturn: '0.0133', cumulativeReturn: '0.0226597', drawdown: '0' },
    { time: '2026-08-01T20:00:00Z', nav: '101360.00', dailyReturn: '-0.0089', cumulativeReturn: '0.0136', drawdown: '-0.0089' },
    { time: '2026-08-08T20:00:00Z', nav: '101620.00', dailyReturn: '0.0026', cumulativeReturn: '0.0162', drawdown: '-0.0063' },
    { time: '2026-08-15T20:00:00Z', nav: '100780.00', dailyReturn: '-0.0083', cumulativeReturn: '0.0078', drawdown: '-0.0145' },
    { time: '2026-08-18T20:00:00Z', nav: '100240.00', dailyReturn: '-0.0054', cumulativeReturn: '0.0024', drawdown: '-0.0198' },
    { time: '2026-08-20T20:00:00Z', nav: '100005.16', dailyReturn: '-0.0023', cumulativeReturn: '0.0000516', drawdown: '-0.0221' },
    { time: '2026-08-21T20:00:00Z', nav: '100425.18', dailyReturn: '0.0042', cumulativeReturn: '0.0042518', drawdown: '-0.0180' },
  ],
  benchmarks: [
    { label: 'Cash', return: '0' },
    { label: 'QQQ', return: '0.0038' },
    { label: 'Equal weight', return: '0.0031' },
    { label: 'Momentum', return: '0.0045' },
  ],
  positions: [
    { symbol: 'NVDA', quantity: '120', marketValue: '15580.80', unrealizedPnl: '425.18', weight: '0.1551', action: 'HOLD' },
    { symbol: 'MSFT', quantity: '20', marketValue: '10144.80', unrealizedPnl: '0.00', weight: '0.1010', action: 'NO_ACTION' },
  ],
  riskDecisions: [
    { id: 'risk-decision-001', orderIntentId: 'intent-nvda-add-001', status: 'REJECTED', reason: 'Position concentration limit would be exceeded.' },
    { id: 'risk-decision-002', orderIntentId: 'intent-msft-hold-001', status: 'ACCEPTED', reason: 'No simulated execution required.' },
  ],
  fills: [
    { id: 'fill-nvda-001', orderId: 'paper-order-nvda-001', symbol: 'NVDA', quantity: '120', price: '126.2968333333333333333333333', eventTime: '2026-07-25T14:31:00Z' },
    { id: 'fill-msft-001', orderId: 'paper-order-msft-001', symbol: 'MSFT', quantity: '20', price: '507.24', eventTime: '2026-07-25T14:32:00Z' },
  ],
  cashLedger: [
    { id: 'ledger-opening-001', kind: 'OPENING_CASH', amount: '100000.00', balance: '100000.00', eventTime: '2026-05-23T20:00:00Z' },
    { id: 'ledger-buy-nvda-001', kind: 'PAPER_BUY', amount: '-15155.62', balance: '84844.38', eventTime: '2026-07-25T14:31:00Z' },
    { id: 'ledger-buy-msft-001', kind: 'PAPER_BUY', amount: '-10144.80', balance: '74699.58', eventTime: '2026-07-25T14:32:00Z' },
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
      category: 'VOLUME',
      symbol: 'NVDA',
      severity: 'HIGH',
      materiality: '0.82',
      summary: 'Relative volume and return z-score crossed the frozen deterministic rule.',
      reviewAction: 'Review thesis invalidation conditions',
      eventTime: '2026-08-21T19:45:00Z',
      thesisId: 'thesis-nvda-v3',
      evidenceId: 'evidence-volume-breakout',
      invalidationConditionId: 'invalidation-nvda-volume-001',
      acknowledged: false,
      explanation: { status: 'FAILED', detail: 'Explanation unavailable; deterministic alert remains valid and visible.' },
    },
    { id: 'alert-aapl-price-001', category: 'PRICE', symbol: 'AAPL', severity: 'MEDIUM', materiality: '0.61', summary: 'Frozen fixture price threshold crossed.', reviewAction: 'Review price evidence', eventTime: '2026-08-21T19:40:00Z', thesisId: 'thesis-aapl-v1', evidenceId: 'evidence-price-001', invalidationConditionId: 'invalidation-aapl-price-001', acknowledged: false, explanation: { status: 'COMPLETED', detail: 'Deterministic price rule.' } },
    { id: 'alert-nvda-options-001', category: 'OPTIONS', symbol: 'NVDA', severity: 'LOW', materiality: '0.42', summary: 'Options coverage became unavailable.', reviewAction: 'Review evidence gap', eventTime: '2026-08-21T19:35:00Z', thesisId: 'thesis-nvda-v3', evidenceId: 'evidence-options-gap', invalidationConditionId: 'invalidation-nvda-options-001', acknowledged: false, explanation: { status: 'DISABLED', detail: 'No free-form explanation requested.' } },
    { id: 'alert-msft-earnings-001', category: 'EARNINGS', symbol: 'MSFT', severity: 'MEDIUM', materiality: '0.58', summary: 'Frozen earnings window entered.', reviewAction: 'Review earnings cutoff', eventTime: '2026-08-21T19:30:00Z', thesisId: 'thesis-msft-v2', evidenceId: 'evidence-earnings-001', invalidationConditionId: 'invalidation-msft-earnings-001', acknowledged: false, explanation: { status: 'COMPLETED', detail: 'Calendar rule.' } },
    { id: 'alert-amd-news-001', category: 'NEWS', symbol: 'AMD', severity: 'LOW', materiality: '0.36', summary: 'Frozen fixture news item linked.', reviewAction: 'Review cited news', eventTime: '2026-08-21T19:25:00Z', thesisId: 'thesis-amd-v1', evidenceId: 'evidence-news-001', invalidationConditionId: 'invalidation-amd-news-001', acknowledged: false, explanation: { status: 'COMPLETED', detail: 'News linkage rule.' } },
    { id: 'alert-aapl-target-001', category: 'ANALYST_TARGET', symbol: 'AAPL', severity: 'LOW', materiality: '0.31', summary: 'Analyst target record changed in fixture.', reviewAction: 'Review target provenance', eventTime: '2026-08-21T19:20:00Z', thesisId: 'thesis-aapl-v1', evidenceId: 'evidence-target-001', invalidationConditionId: 'invalidation-aapl-target-001', acknowledged: false, explanation: { status: 'COMPLETED', detail: 'Target-change rule.' } },
    { id: 'alert-portfolio-risk-001', category: 'PORTFOLIO_RISK', symbol: 'PORTFOLIO', severity: 'HIGH', materiality: '0.87', summary: 'Proposed concentration breached the frozen risk policy.', reviewAction: 'Review rejected RiskDecision', eventTime: '2026-08-21T19:15:00Z', thesisId: 'thesis-nvda-v3', evidenceId: 'risk-decision-001', invalidationConditionId: 'invalidation-nvda-concentration-001', acknowledged: false, explanation: { status: 'COMPLETED', detail: 'Deterministic portfolio-risk rule.' } },
  ],
}

export const fixtureWeeklyReviewSnapshot: WeeklyReviewSnapshot = {
  asOf: '2026-08-21T20:00:00Z',
  outcomes: [
    { symbol: 'NVDA', horizon: '5 day', return: '0.031', confidence: '0.74', thesisHit: 'HIT' },
    { symbol: 'MSFT', horizon: '5 day', return: '-0.006', confidence: '0.69', thesisHit: 'MISS' },
  ],
  calibration: [
    { bucket: '70–79% confidence', decisionCount: 1, observedHitRate: '1.00' },
    { bucket: '60–69% confidence', decisionCount: 1, observedHitRate: '0.00' },
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
