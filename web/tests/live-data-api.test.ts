import { describe, expect, it, vi } from 'vitest'

import {
  getDataQuality,
  getMarketQuotes,
  getPortfolioSummary,
  getProviderHealth,
  getStockResearch,
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
