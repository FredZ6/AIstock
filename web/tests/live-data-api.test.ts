import { describe, expect, it, vi } from 'vitest'

import {
  createResearchRun,
  getAlerts,
  getDataQuality,
  getEvalRunDetail,
  getEvalRuns,
  getMarketQuotes,
  getLatestResearchRun,
  getPortfolioSummary,
  getProviderHealth,
  getStockResearch,
  getResearchRunReport,
  getWeeklyReviewDetail,
  initializePortfolio,
  LiveDataApiError,
} from '../lib/server/live-data-api'

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

const options = { baseUrl: 'http://api.test', decisionTime: '2026-08-29T09:30:00Z' }

describe('live data API client', () => {
  it('parses version-pinned evaluation runs, metrics, and gates', async () => {
    const run = {
      id: '10000000-0000-0000-0000-000000000099', status: 'PASSED', passed: true,
      mode: 'fixture', dataset_version: 'eval-v0.2.0', case_count: 200,
      data_cutoff: '2026-08-21T20:00:00Z', model_version: 'fixture-deterministic-v1',
      prompt_version: 'offline-eval-v0.2', research_scoring_policy_version: 'research-v1',
      risk_policy_version: 'risk-v1', execution_policy_version: 'execution-v1',
      confidence_policy_version: 'confidence-v1', gate_policy_version: 'gates-v1',
      summary_hash: 'a'.repeat(64), created_at: '2026-08-29T09:20:00Z',
    }
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ items: [run], next_cursor: null, decision_time: options.decisionTime }))
      .mockResolvedValueOnce(jsonResponse({
        decision_time: options.decisionTime, run,
        metrics: [{ metric_name: 'directional_accuracy', metric_value: '0.91', case_ids: ['r1'], case_hashes: ['b'.repeat(64)] }],
        gates: [{ metric_name: 'directional_accuracy', comparison: 'AT_LEAST', threshold: '0.8', observed: '0.91', passed: true, reason: 'meets threshold' }],
      }))

    const page = await getEvalRuns({ ...options, fetchImpl })
    await expect(getEvalRunDetail({ ...options, fetchImpl }, page.items[0].id)).resolves.toMatchObject({
      run: { caseCount: 200, modelVersion: 'fixture-deterministic-v1' },
      metrics: [{ name: 'directional_accuracy', value: '0.91' }],
      gates: [{ comparison: 'AT_LEAST', passed: true }],
    })
  })

  it('parses the locked point-in-time Alert contract without weakening Decimal or timestamp fields', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      decision_time: options.decisionTime,
      items: [{
        acknowledged_at: null,
        acknowledged_by: null,
        alert_key: 'NVDA:price-gap:2026-08-29',
        conditions: [{ operator: 'gte', threshold: '0.05' }],
        correlation_id: '10000000-0000-0000-0000-000000000099',
        created_at: '2026-08-29T09:21:00Z',
        data_quality: { coverage: 'IEX', freshness: 'PT1M' },
        event_time: '2026-08-29T09:20:00Z',
        id: '10000000-0000-0000-0000-000000000001',
        materiality: '0.075',
        metrics: { move: '0.081' },
        rule_id: 'price-gap',
        rule_version: 'price-gap-v2',
        severity: 'HIGH',
        symbol: 'NVDA',
      }],
      next_cursor: null,
    }))

    await expect(getAlerts({ ...options, fetchImpl })).resolves.toEqual({
      items: [expect.objectContaining({
        alertKey: 'NVDA:price-gap:2026-08-29',
        correlationId: '10000000-0000-0000-0000-000000000099',
        createdAt: '2026-08-29T09:21:00Z',
        dataQuality: { coverage: 'IEX', freshness: 'PT1M' },
        eventTime: '2026-08-29T09:20:00Z',
        materiality: '0.075',
        ruleId: 'price-gap',
        ruleVersion: 'price-gap-v2',
        severity: 'HIGH',
        symbol: 'NVDA',
      })],
      nextCursor: null,
    })
  })

  it('rejects malformed Alert Decimal and naive datetime values', async () => {
    const invalid = {
      acknowledged_at: null,
      acknowledged_by: null,
      alert_key: 'NVDA:price-gap:2026-08-29',
      conditions: [],
      correlation_id: '10000000-0000-0000-0000-000000000099',
      created_at: '2026-08-29T09:21:00Z',
      data_quality: {},
      event_time: '2026-08-29T09:20:00',
      id: '10000000-0000-0000-0000-000000000001',
      materiality: 0.075,
      metrics: {},
      rule_id: 'price-gap',
      rule_version: 'price-gap-v2',
      severity: 'HIGH',
      symbol: 'NVDA',
    }
    const fetchImpl = vi.fn(async () => jsonResponse({ items: [invalid], next_cursor: null }))

    await expect(getAlerts({ ...options, fetchImpl })).rejects.toMatchObject({ kind: 'contract' })
  })

  it('loads the latest research run at the requested point-in-time cutoff', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      data_cutoff: options.decisionTime,
      decision_time: options.decisionTime,
      run_id: '10000000-0000-0000-0000-000000000099',
      run_type: 'RESEARCH',
      status: 'RUNNING',
      symbol: 'NVDA',
    }))

    await expect(getLatestResearchRun({ ...options, fetchImpl })).resolves.toMatchObject({ symbol: 'NVDA' })
    expect(fetchImpl).toHaveBeenCalledWith(
      `http://api.test/api/v1/research-runs/latest?decision_time=${encodeURIComponent(options.decisionTime)}`,
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('parses the closed research report without weakening Decimal or timestamp contracts', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      run_id: 'run-1',
      thesis: { id: 'thesis-1', symbol: 'NVDA', as_of: options.decisionTime, direction: 'UP', summary: 'Durable demand.', catalysts: [], risks: [], invalidation_conditions: [], horizon: '12M', confidence: '0.82', supersedes_thesis_id: null, created_at: options.decisionTime },
      opinion: { id: 'opinion-1', value: 'BULLISH', created_at: options.decisionTime },
      decision: { id: 'decision-1', data_cutoff: options.decisionTime, available_at: options.decisionTime, prompt_version: 'prompt-v1', model_version: 'model-v1', policy_versions: { research_scoring: 'score-v1', risk: 'risk-v1', execution: 'paper-v1', confidence: 'confidence-v1' }, created_at: options.decisionTime },
      evidence: [{ id: 'evidence-1', relation: 'SUPPORTS', weight: '1', rationale: 'Filed fact.', claims: ['Revenue grew'], provider: 'SEC', feed_type: 'FINANCIALS', event_time: options.decisionTime, available_at: options.decisionTime, ingested_at: options.decisionTime, content_hash: 'abc', raw_object_key: 'sec/raw.json' }],
      evidence_gaps: [],
      decision_diff: { id: 'diff-1', decision_id: 'decision-1', previous_decision_id: null, generator: 'DETERMINISTIC_CODE', changes: {}, created_at: options.decisionTime },
    }))

    await expect(getResearchRunReport({ ...options, fetchImpl }, 'run-1')).resolves.toMatchObject({
      thesis: { confidence: '0.82' },
      evidence: [{ rawObjectKey: 'sec/raw.json' }],
      decisionDiff: { generator: 'DETERMINISTIC_CODE' },
    })
  })

  it('admits a research run with one point-in-time cutoff and a stable idempotency key', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      data_cutoff: options.decisionTime,
      decision_time: options.decisionTime,
      run_id: '10000000-0000-0000-0000-000000000099',
      run_type: 'RESEARCH',
      status: 'QUEUED',
      symbol: 'NVDA',
    }, 202))

    await expect(createResearchRun(
      { ...options, fetchImpl },
      'NVDA',
      'research-form-1',
    )).resolves.toMatchObject({ runId: '10000000-0000-0000-0000-000000000099' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api.test/api/v1/research-runs',
      expect.objectContaining({
        body: JSON.stringify({
          data_cutoff: options.decisionTime,
          decision_time: options.decisionTime,
          symbol: 'NVDA',
        }),
        headers: expect.objectContaining({ 'Idempotency-Key': 'research-form-1' }),
        method: 'POST',
      }),
    )
  })

  it('rejects invalid research admission input before calling FastAPI', async () => {
    const fetchImpl = vi.fn()

    await expect(createResearchRun(
      { ...options, fetchImpl },
      'nvda!',
      'research-form-1',
    )).rejects.toMatchObject({ kind: 'contract' })
    await expect(createResearchRun(
      { ...options, fetchImpl },
      'NVDA',
      '',
    )).rejects.toMatchObject({ kind: 'contract' })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('validates point-in-time quote Decimal strings and provenance', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      status: 'SUCCESS',
      decision_time: options.decisionTime,
      missing_symbols: [],
      items: [{
        symbol: 'NVDA', provider: 'ALPACA', coverage: 'IEX', feed_type: 'price_bars',
        event_time: '2026-08-28T04:00:00Z', available_at: '2026-08-29T09:20:00Z',
        ingested_at: '2026-08-29T09:20:01Z', content_hash: 'a'.repeat(64),
        raw_object_key: `live/ALPACA/price_bars/${'a'.repeat(64)}.json`, close: '217.545',
        open: '220', high: '221', low: '216', volume: '5357434', session: 'REGULAR',
      }],
    }))

    const result = await getMarketQuotes({ ...options, fetchImpl }, ['NVDA'])

    expect(result.items[0]).toMatchObject({ symbol: 'NVDA', close: '217.545', provider: 'ALPACA' })
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/market-data/quotes?'),
      expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }),
    )
  })

  it('rejects malformed provider responses instead of substituting fixtures', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ status: 'SUCCESS', items: [{ close: 217.5 }] }))

    await expect(getMarketQuotes({ ...options, fetchImpl }, ['NVDA'])).rejects.toMatchObject({
      kind: 'contract',
    })
  })

  it('loads runtime provider health, portfolio facts, and persisted research independently', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/providers/health')) return jsonResponse({
        mode: 'paper',
        providers: {
          alpaca: { configured: true, mode: 'read_only', status: 'FAILURE', coverage: 'IEX' },
          alpha_vantage: { configured: false, mode: 'unavailable', status: null, coverage: null },
          sec: { configured: false, mode: 'unavailable', status: null, coverage: null },
        },
      })
      if (url.includes('/portfolio?')) return jsonResponse({
        cash: null, cash_ledger: [], configuration: null, decision_time: options.decisionTime,
        fills: [], initialized_at: null, latest_nav: null, orders: [], performance_history: [],
        positions: [], risk_decisions: [], status: 'EMPTY', trading: 'paper_only',
      })
      return jsonResponse({
        decision_time: options.decisionTime, financial_facts: [], items: [],
        next_cursor: null, sec_filings: [],
      })
    })

    await expect(getProviderHealth({ ...options, fetchImpl })).resolves.toMatchObject({
      mode: 'paper',
      providers: {
        alpaca: { status: 'FAILURE' },
        alpha_vantage: { status: undefined },
        sec: { status: undefined },
      },
    })
    await expect(getPortfolioSummary({ ...options, fetchImpl })).resolves.toMatchObject({
      cash: null, latestNav: null, status: 'EMPTY', trading: 'paper_only',
    })
    await expect(getStockResearch({ ...options, fetchImpl }, 'NVDA')).resolves.toEqual({
      financialFacts: [], records: [], secFilings: [],
    })
  })

  it('parses the complete point-in-time paper portfolio contract without numeric money', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      cash: { balance: '90500', currency: 'USD' },
      cash_ledger: [{ account: 'CASH', created_at: '2026-08-29T09:20:00Z', credit: '0', currency: 'USD', debit: '9500', id: 'ledger-1', idempotency_key: 'fill-1:cash', occurred_at: '2026-08-29T09:20:00Z', reversal_of_id: null, source_id: 'fill-1', transaction_id: 'transaction-1' }],
      configuration: { currency: 'USD', id: 'portfolio-1', initial_cash: '100000', name: 'default-paper' },
      decision_time: options.decisionTime,
      fills: [{ created_at: '2026-08-29T09:20:00Z', currency: 'USD', execution_policy_version_id: 'execution-v1', fee: '0', filled_at: '2026-08-29T09:20:00Z', id: 'fill-1', idempotency_key: 'fill-1', order_id: 'order-1', portfolio_id: 'portfolio-1', price: '190', quantity: '50', reversal_of_id: null, side: 'BUY', source_bar_time: '2026-08-29T09:19:00Z', symbol: 'NVDA' }],
      initialized_at: '2026-08-28T09:00:00Z',
      latest_nav: { available_at: '2026-08-29T09:21:00Z', event_time: '2026-08-29T09:20:00Z', id: 'nav-2', nav: '100500', portfolio_id: 'portfolio-1' },
      orders: [],
      performance_history: [
        { available_at: '2026-08-28T09:01:00Z', event_time: '2026-08-28T09:00:00Z', id: 'nav-1', nav: '101000', portfolio_id: 'portfolio-1' },
        { available_at: '2026-08-29T09:21:00Z', event_time: '2026-08-29T09:20:00Z', id: 'nav-2', nav: '100500', portfolio_id: 'portfolio-1' },
      ],
      positions: [{ average_cost: '190', market_price: '200', market_value: '10000', price_available_at: '2026-08-29T09:19:00Z', quantity: '50', symbol: 'NVDA', unrealized_pnl: '500' }],
      risk_decisions: [{ approved_delta: '0.1', approved_weight: '0.1', authorization_source: 'policy', authorized_side: 'BUY', created_at: '2026-08-29T09:18:00Z', current_weight: '0', decided_at: '2026-08-29T09:18:00Z', id: 'risk-1', market_context_snapshot_id: 'context-1', max_order_quantity: '50', portfolio_id: 'portfolio-1', proposal_id: 'proposal-1', reason_codes: [], reference_nav: '100000', reference_price: '190', research_decision_id: 'research-1', requested_weight: '0.1', risk_policy_version_id: 'risk-v1', status: 'APPROVED', symbol: 'NVDA' }],
      status: 'SUCCESS', trading: 'paper_only',
    }))

    await expect(getPortfolioSummary({ ...options, fetchImpl })).resolves.toMatchObject({
      cashLedger: [{ debit: '9500', occurredAt: '2026-08-29T09:20:00Z' }],
      fills: [{ price: '190', quantity: '50', symbol: 'NVDA' }],
      performanceHistory: [{ nav: '101000' }, { availableAt: '2026-08-29T09:21:00Z', nav: '100500' }],
      positions: [{ marketValue: '10000', unrealizedPnl: '500' }],
      riskDecisions: [{ approvedWeight: '0.1', status: 'APPROVED' }],
    })

    const invalidFetch = vi.fn(async () => jsonResponse({
      cash: null, cash_ledger: [], configuration: null, decision_time: options.decisionTime,
      fills: [], initialized_at: null, latest_nav: null, orders: [], performance_history: [],
      positions: [{ average_cost: 190, market_price: null, market_value: null, price_available_at: null, quantity: '50', symbol: 'NVDA', unrealized_pnl: null }],
      risk_decisions: [], status: 'SUCCESS', trading: 'paper_only',
    }))
    await expect(getPortfolioSummary({ ...options, fetchImpl: invalidFetch })).rejects.toMatchObject({ kind: 'contract' })
  })

  it('loads point-in-time SEC data-quality dimensions without deriving a UI grade', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      decision_time: options.decisionTime,
      items: [{
        conflict: false, coverage: null, created_at: options.decisionTime,
        dataset: 'company_facts', delay: null, details: {}, dimension: 'FRESHNESS',
        freshness: 'PT0S', id: 'quality-1', normalized_record_id: 'record-1',
        observed_at: '2026-08-29T09:20:00Z', policy_version: 'quality-v1', provider: 'SEC',
        raw_data_object_id: 'raw-1', status: 'PASS',
      }, {
        conflict: false, coverage: null, created_at: '2026-08-29T09:00:00Z',
        dataset: 'company_facts', delay: null, details: {}, dimension: 'FRESHNESS',
        freshness: 'PT10M', id: 'quality-old', normalized_record_id: 'record-old',
        observed_at: '2026-08-29T09:00:00Z', policy_version: 'quality-v1', provider: 'SEC',
        raw_data_object_id: 'raw-old', status: 'DEGRADED',
      }],
      status: 'SUCCESS',
    }))

    await expect(getDataQuality({ ...options, fetchImpl }, 'SEC', 'company_facts')).resolves.toEqual([{
      conflict: false, coverage: null, dataset: 'company_facts', delay: null,
      dimension: 'FRESHNESS', freshness: 'PT0S', id: 'quality-1',
      observedAt: '2026-08-29T09:20:00Z', provider: 'SEC', status: 'PASS',
    }])
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/data-quality?'),
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('classifies network and HTTP failures without exposing upstream bodies', async () => {
    const network = vi.fn(async () => { throw new TypeError('private network detail') })
    await expect(getProviderHealth({ ...options, fetchImpl: network })).rejects.toMatchObject({ kind: 'unavailable' })

    const response = vi.fn(async () => new Response('private upstream body', { status: 503 }))
    const error = await getProviderHealth({ ...options, fetchImpl: response }).catch((caught) => caught)
    expect(error).toBeInstanceOf(LiveDataApiError)
    expect(error).toMatchObject({ kind: 'response', status: 503 })
    expect((error as Error).message).not.toContain('private upstream body')
  })

  it('initializes only the singleton paper portfolio with an idempotency key', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      currency: 'USD',
      initial_cash: '100000',
      initialized_at: options.decisionTime,
      name: 'default-paper',
      portfolio_id: '10000000-0000-0000-0000-000000000001',
      status: 'READY',
    }))

    await expect(initializePortfolio({ ...options, fetchImpl }, 'initialize-default-paper-v1'))
      .resolves.toMatchObject({ initialCash: '100000', status: 'READY' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://api.test/api/v1/portfolio/initialize',
      expect.objectContaining({
        body: JSON.stringify({ effective_at: options.decisionTime }),
        method: 'POST',
        headers: expect.objectContaining({ 'Idempotency-Key': 'initialize-default-paper-v1' }),
      }),
    )
  })

  it('parses normalized weekly review detail without accepting numeric Decimal fields', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({
      approvals: [],
      attributions: [{ category: 'TIMING_ERROR', controllable: true, created_at: options.decisionTime, id: 'a1', outcome_id: 'o1', rationale: 'Late entry.' }],
      calibration: [{ calibration_error: '0.2', confidence: '0.8', decision_id: 'd1', realized_return: '0.03', status: 'MATURED' }],
      decision_time: options.decisionTime,
      lessons: [{ attribution_id: 'a1', confidence: '0.7', counter_evidence: [], created_at: options.decisionTime, creator: 'weekly-review', evidence: ['o1'], id: 'l1', replay_delta: '0.1', scope: 'TIMING', statement: 'Wait for confirmation.', status: 'CANDIDATE' }],
      outcomes: [{ calibration_error: '0.2', computed_at: options.decisionTime, confidence: '0.8', created_at: options.decisionTime, decision_id: 'd1', excess_returns: {}, id: 'o1', maximum_adverse_excursion: '-0.01', maximum_favorable_excursion: '0.04', opinion: 'BULLISH', returns: { '1': '0.03' }, risk_adjusted_return: '3', status: 'MATURED', symbol: 'NVDA' }],
      replays: [],
      review: { confidence_policy_version: 'confidence-v1', created_at: options.decisionTime, data_cutoff: options.decisionTime, decision_ids: ['d1'], decision_time: options.decisionTime, execution_policy_version: 'execution-v1', id: 'r1', model_version: 'model-v1', prompt_version: 'prompt-v1', research_scoring_policy_version: 'research-v1', risk_policy_version: 'risk-v1', run_key: 'run-1', status: 'COMPLETED' },
    }))

    await expect(getWeeklyReviewDetail({ ...options, fetchImpl }, 'r1')).resolves.toMatchObject({
      outcomes: [{ confidence: '0.8', symbol: 'NVDA' }],
      calibration: [{ realizedReturn: '0.03' }],
      lessons: [{ statement: 'Wait for confirmation.' }],
    })
  })
})
