import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ApiAlertsPage, ApiPortfolioPage, ApiResearchPage, ApiRunMetadataPage, ApiTodayPage, ApiWeeklyReviewPage } from '../components/live/api-pages'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

const quote = {
  availableAt: '2026-08-29T09:20:00Z',
  close: '217.545',
  coverage: 'IEX' as const,
  eventTime: '2026-08-28T04:00:00Z',
  provider: 'ALPACA',
  symbol: 'NVDA',
}
const health = {
  mode: 'paper' as const,
  providers: {
    alpaca: { configured: true, coverage: 'IEX', mode: 'read_only' as const, status: 'SUCCESS' as const },
    sec: { configured: false, coverage: null, mode: 'unavailable' as const },
  },
}
const emptyPortfolio = {
  cash: null,
  cashLedger: [],
  configuration: { currency: 'USD' as const, id: 'portfolio-1', initialCash: '100000', name: 'default-paper' },
  fills: [],
  initializedAt: null,
  latestNav: null,
  orders: [],
  performanceHistory: [],
  positions: [],
  riskDecisions: [],
  status: 'EMPTY' as const,
  trading: 'paper_only' as const,
}

describe('API mode pages', () => {
  it('renders persisted Alerts as actionable point-in-time evidence instead of a count placeholder', () => {
    render(<ApiAlertsPage asOf="2026-08-29T09:30:00Z" alerts={[{
      acknowledgedAt: null,
      acknowledgedBy: null,
      alertKey: 'NVDA:price-gap:2026-08-29',
      conditions: [{ operator: 'gte', threshold: '0.05' }],
      correlationId: '10000000-0000-0000-0000-000000000099',
      createdAt: '2026-08-29T09:21:00Z',
      dataQuality: { coverage: 'IEX', freshness: 'PT1M' },
      eventTime: '2026-08-29T09:20:00Z',
      id: '10000000-0000-0000-0000-000000000001',
      materiality: '0.075',
      metrics: { move: '0.081' },
      ruleId: 'price-gap',
      ruleVersion: 'price-gap-v2',
      severity: 'HIGH',
      symbol: 'NVDA',
    }]} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
    expect(screen.getByText('HIGH')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'NVDA research' })).toHaveAttribute('href', '/research/NVDA')
    expect(screen.getByText('7.50%')).toBeInTheDocument()
    expect(screen.getByText('price-gap · price-gap-v2')).toBeInTheDocument()
    expect(screen.getByText('Not acknowledged')).toBeInTheDocument()
    expect(screen.getByText(/10000000-0000-0000-0000-000000000099/)).toBeInTheDocument()
    expect(screen.getByText(/"coverage": "IEX"/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open latest run trace' })).toHaveAttribute('href', '/runs/latest')
    expect(screen.queryByText(/Detailed presentation remains constrained/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Fixture Mode/)).not.toBeInTheDocument()
  })

  it('renders the closed persisted report with lineage, gaps, pins, and deterministic diff', () => {
    render(<ApiRunMetadataPage run={{
      dataCutoff: '2026-09-06T14:00:00Z', decisionTime: '2026-09-06T14:00:00Z',
      runId: 'run-1', runType: 'RESEARCH', status: 'COMPLETED', symbol: 'NVDA',
    }} report={{
      runId: 'run-1',
      thesis: { id: 'thesis-1', symbol: 'NVDA', asOf: '2026-09-06T14:00:00Z', direction: 'UP', summary: 'Demand remains durable.', catalysts: ['Blackwell'], risks: ['Supply'], invalidationConditions: ['Margin decline'], horizon: '12M', confidence: '0.82', supersedesThesisId: null, createdAt: '2026-09-06T14:00:02Z' },
      opinion: { id: 'opinion-1', value: 'BULLISH', createdAt: '2026-09-06T14:00:02Z' },
      decision: { id: 'decision-1', dataCutoff: '2026-09-06T14:00:00Z', availableAt: '2026-09-06T14:00:02Z', promptVersion: 'prompt-v1', modelVersion: 'deterministic-v1', policyVersions: { researchScoring: 'score-v1', risk: 'risk-v1', execution: 'paper-v1', confidence: 'confidence-v1' }, createdAt: '2026-09-06T14:00:02Z' },
      evidence: [{ id: 'evidence-1', relation: 'SUPPORTS', weight: '0.9', rationale: 'Revenue acceleration.', claims: ['Revenue grew'], provider: 'SEC', feedType: 'FINANCIALS', eventTime: '2026-09-05T20:00:00Z', availableAt: '2026-09-05T20:01:00Z', ingestedAt: '2026-09-05T20:02:00Z', contentHash: 'abc123', rawObjectKey: 'sec/raw/abc.json' }],
      evidenceGaps: [{ id: 'gap-1', runId: 'run-1', kind: 'UNAVAILABLE', field: 'options', domain: 'DERIVATIVES', reason: 'Provider not configured', provider: null, observedAt: '2026-09-06T14:00:01Z', createdAt: '2026-09-06T14:00:02Z' }],
      decisionDiff: { id: 'diff-1', decisionId: 'decision-1', previousDecisionId: null, generator: 'DETERMINISTIC_CODE', changes: { opinion: { after: 'BULLISH' } }, createdAt: '2026-09-06T14:00:02Z' },
    }} />)

    expect(screen.getByRole('heading', { name: 'Deterministic Research Workflow' })).toBeInTheDocument()
    expect(screen.getByText('Demand remains durable.')).toBeInTheDocument()
    expect(screen.getByText('82.00%')).toBeInTheDocument()
    expect(screen.getByText('sec/raw/abc.json')).toBeInTheDocument()
    expect(screen.getByText('Provider not configured')).toBeInTheDocument()
    expect(screen.getByText('prompt-v1')).toBeInTheDocument()
    expect(screen.getByText('deterministic-v1')).toBeInTheDocument()
    expect(screen.getByText('DETERMINISTIC_CODE')).toBeInTheDocument()
  })

  it('shows real Today facts and explicit degraded domains without a Fixture notice', () => {
    render(<ApiTodayPage asOf="2026-08-29T09:30:00Z" health={health} portfolio={emptyPortfolio} quotes={[quote]} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    expect(screen.getAllByText(/ALPACA · IEX/)).toHaveLength(2)
    expect(screen.getByRole('region', { name: 'Current market reference' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Latest persisted quotes' })).not.toBeInTheDocument()
    const evidence = screen.getByText('Persisted quote evidence · 1 symbol').closest('details')
    expect(evidence).not.toHaveAttribute('open')
    expect(screen.getByText(/TradingView data is external current-market context/)).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Some decision facts are unavailable' })).toHaveTextContent('No Fixture data was substituted')
    expect(screen.queryByText('Fixture Mode')).not.toBeInTheDocument()
  })

  it('keeps current quote visible when persisted research is empty', () => {
    render(<ApiResearchPage asOf="2026-08-29T09:30:00Z" dataQuality={[]} financialFacts={[]} idempotencyKey="research-form-1" quote={quote} records={[]} secFilings={[]} symbol="NVDA" />)

    expect(screen.getByRole('heading', { name: 'NVDA research' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Research evidence unavailable' })).toBeInTheDocument()
    expect(screen.getByText('USD 217.55')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Research symbol' })).toHaveValue('NVDA')
    expect(screen.getByRole('button', { name: 'Run deterministic research' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('research-form-1')).toHaveAttribute('type', 'hidden')
    expect(screen.queryByText(/run with (openai|anthropic|llm)/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /broker|trade|order/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/frozen fixture/i)).not.toBeInTheDocument()
  })

  it('renders persisted SEC filings and financial facts with source and availability', () => {
    render(<ApiResearchPage
      asOf="2026-08-29T09:30:00Z"
      dataQuality={[{
        conflict: false, coverage: null, dataset: 'company_facts', delay: null,
        dimension: 'FRESHNESS', freshness: 'PT0S', id: 'quality-1',
        observedAt: '2026-08-29T09:20:00Z', provider: 'SEC', status: 'PASS',
      }]}
      financialFacts={[{
        accessionNumber: '0001045810-26-000001', availableAt: '2026-08-28T20:05:00Z',
        canonicalConcept: 'REVENUE', currency: 'USD', id: 'fact-1', mappingStatus: 'EXACT',
        periodEnd: '2026-07-31', periodStart: '2026-05-01', provider: 'SEC',
        sourceConcept: 'Revenues', taxonomy: 'us-gaap', unit: 'USD', value: '9007199254740993',
      }]}
      idempotencyKey="research-form-2"
      quote={quote}
      records={[]}
      secFilings={[{
        acceptedAt: '2026-08-28T20:05:00Z', accessionNumber: '0001045810-26-000001',
        availableAt: '2026-08-28T20:05:00Z', description: 'Quarterly report',
        documentRawObjectKey: 'live/SEC/filing_sections/hash.txt', filingDate: '2026-08-28',
        form: '10-Q', id: 'filing-1', provider: 'SEC', reportDate: '2026-07-31',
      }]}
      symbol="NVDA"
    />)
    expect(screen.getByRole('heading', { name: 'SEC filings' })).toBeInTheDocument()
    expect(screen.getAllByText('0001045810-26-000001')).toHaveLength(2)
    expect(screen.getByText('REVENUE')).toBeInTheDocument()
    expect(screen.getByText('9,007,199,254,740,993 USD')).toBeInTheDocument()
    expect(screen.getByText('live/SEC/filing_sections/hash.txt')).toBeInTheDocument()
    expect(screen.getByText('FRESHNESS')).toBeInTheDocument()
    expect(screen.getByText('PASS')).toBeInTheDocument()
    expect(screen.getByText('SEC filings · 1').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Financial facts · 1').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('SEC data quality · 1').closest('details')).not.toHaveAttribute('open')
    expect(screen.queryByText('Fixture Mode')).not.toBeInTheDocument()
  })

  it('leads with one latest conclusion and keeps older decisions subordinate', () => {
    const latest = {
      asOf: '2026-08-29T09:00:00Z', confidence: '0.82', direction: 'UP', horizon: '12M',
      id: 'thesis-latest', opinion: 'BULLISH' as const, summary: 'Latest durable demand thesis.', symbol: 'NVDA',
    }
    const previous = {
      asOf: '2026-08-20T09:00:00Z', confidence: '0.30', direction: 'FLAT', horizon: '3M',
      id: 'thesis-previous', opinion: 'ABSTAIN' as const, summary: 'Previous uncertain thesis.', symbol: 'NVDA',
    }
    render(<ApiResearchPage
      asOf="2026-08-29T09:30:00Z"
      dataQuality={[]}
      financialFacts={[]}
      idempotencyKey="research-form-hierarchy"
      quote={quote}
      records={[latest, previous]}
      secFilings={[]}
      symbol="NVDA"
    />)

    const conclusion = screen.getByRole('region', { name: 'Latest research conclusion' })
    expect(conclusion).toHaveTextContent('BULLISH')
    expect(conclusion).toHaveTextContent('82.00%')
    expect(conclusion).toHaveTextContent(latest.summary)
    expect(conclusion).not.toHaveTextContent('ABSTAIN')
    const history = screen.getByText('Decision history · 1 previous').closest('details')
    expect(history).not.toHaveAttribute('open')
    expect(history).toHaveTextContent('ABSTAIN')
    expect(history).toHaveTextContent('30.00%')
    const currentMarket = screen.getByRole('region', { name: 'Current market reference' })
    expect(conclusion.compareDocumentPosition(currentMarket) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows an empty persisted paper portfolio without inventing NAV or ledger facts', () => {
    render(<ApiPortfolioPage asOf="2026-08-29T09:30:00Z" portfolio={emptyPortfolio} />)

    expect(screen.getByRole('heading', { name: 'AI Portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Paper portfolio not initialized' })).toHaveTextContent('USD 100,000')
    expect(screen.getByRole('button', { name: 'Initialize USD 100,000 paper portfolio' })).toBeInTheDocument()
    expect(screen.queryByText('$100,425.18')).not.toBeInTheDocument()
  })

  it('shows initialized cash as success even before the first NAV snapshot', () => {
    render(<ApiPortfolioPage
      asOf="2026-08-29T09:30:00Z"
      portfolio={{ ...emptyPortfolio, cash: { balance: '100000', currency: 'USD' }, initializedAt: '2026-08-29T09:00:00Z', status: 'SUCCESS' }}
    />)

    expect(screen.getByText('USD 100,000.00')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Initialize USD/ })).not.toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Portfolio evidence is partial' })).toBeInTheDocument()
  })

  it('labels the persisted API portfolio snapshot and evidence availability explicitly', () => {
    render(<ApiPortfolioPage
      asOf="2026-08-29T09:30:00Z"
      portfolio={{ ...emptyPortfolio, cash: { balance: '100000', currency: 'USD' }, initializedAt: '2026-08-29T09:00:00Z', status: 'SUCCESS' }}
    />)

    const summary = screen.getByRole('region', { name: 'Portfolio snapshot' })
    expect(within(summary).getByText('Net asset value').parentElement).toHaveTextContent('Unavailable')
    expect(within(summary).getByText('Available cash').parentElement).toHaveTextContent('USD 100,000.00')
    expect(summary).toHaveTextContent('As of')
    const evidence = screen.getByRole('region', { name: 'Paper trading evidence availability' })
    expect(within(evidence).getByText('Positions').parentElement).toHaveTextContent('0')
  })

  it('treats authoritative zero activity as empty history rather than missing evidence', () => {
    render(<ApiPortfolioPage
      asOf="2026-08-29T09:30:00Z"
      portfolio={{
        ...emptyPortfolio,
        cash: { balance: '100000', currency: 'USD' },
        initializedAt: '2026-08-29T09:00:00Z',
        latestNav: { availableAt: '2026-08-29T09:00:00Z', eventTime: '2026-08-29T09:00:00Z', id: 'nav-1', nav: '100000', portfolioId: 'portfolio-1' },
        performanceHistory: [{ availableAt: '2026-08-29T09:00:00Z', eventTime: '2026-08-29T09:00:00Z', id: 'nav-1', nav: '100000', portfolioId: 'portfolio-1' }],
        status: 'SUCCESS',
      }}
    />)

    expect(screen.queryByRole('status', { name: 'Portfolio evidence is partial' })).not.toBeInTheDocument()
    expect(screen.getByText('Positions').parentElement).toHaveTextContent('0')
    expect(screen.getByText('Cash ledger entries').parentElement).toHaveTextContent('0')
  })

  it('renders Decimal-derived portfolio analytics and normalized audit evidence', () => {
    render(<ApiPortfolioPage
      asOf="2026-08-29T09:30:00Z"
      portfolio={{
        ...emptyPortfolio,
        cash: { balance: '90500', currency: 'USD' },
        initializedAt: '2026-08-28T09:00:00Z',
        latestNav: { availableAt: '2026-08-29T09:21:00Z', eventTime: '2026-08-29T09:20:00Z', id: 'nav-2', nav: '100500', portfolioId: 'portfolio-1' },
        performanceHistory: [
          { availableAt: '2026-08-28T09:01:00Z', eventTime: '2026-08-28T09:00:00Z', id: 'nav-1', nav: '101000', portfolioId: 'portfolio-1' },
          { availableAt: '2026-08-29T09:21:00Z', eventTime: '2026-08-29T09:20:00Z', id: 'nav-2', nav: '100500', portfolioId: 'portfolio-1' },
        ],
        positions: [{ averageCost: '190', marketPrice: '200', marketValue: '10000', priceAvailableAt: '2026-08-29T09:19:00Z', quantity: '50', symbol: 'NVDA', unrealizedPnl: '500' }],
        riskDecisions: [{ approvedDelta: '0.1', approvedWeight: '0.1', authorizationSource: 'policy', authorizedSide: 'BUY', createdAt: '2026-08-29T09:18:00Z', currentWeight: '0', decidedAt: '2026-08-29T09:18:00Z', id: 'risk-1', marketContextSnapshotId: 'context-1', maxOrderQuantity: '50', portfolioId: 'portfolio-1', proposalId: 'proposal-1', reasonCodes: [], referenceNav: '100000', referencePrice: '190', researchDecisionId: 'research-1', requestedWeight: '0.1', riskPolicyVersionId: 'risk-v1', status: 'APPROVED', symbol: 'NVDA' }],
        fills: [{ createdAt: '2026-08-29T09:20:00Z', currency: 'USD', executionPolicyVersionId: 'execution-v1', fee: '0', filledAt: '2026-08-29T09:20:00Z', id: 'fill-1', idempotencyKey: 'fill-1', orderId: 'order-1', portfolioId: 'portfolio-1', price: '190', quantity: '50', reversalOfId: null, side: 'BUY', sourceBarTime: '2026-08-29T09:19:00Z', symbol: 'NVDA' }],
        cashLedger: [{ account: 'CASH', createdAt: '2026-08-29T09:20:00Z', credit: '0', currency: 'USD', debit: '9500', id: 'ledger-1', idempotencyKey: 'fill-1:cash', occurredAt: '2026-08-29T09:20:00Z', reversalOfId: null, sourceId: 'fill-1', transactionId: 'transaction-1' }],
        status: 'SUCCESS',
      }}
    />)

    expect(screen.getByText('Day return').parentElement).toHaveTextContent('-0.50%')
    expect(screen.getByText('Current drawdown').parentElement).toHaveTextContent('-0.50%')
    expect(screen.getByRole('img', { name: 'Net asset value history' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Paper positions' })).toHaveTextContent('USD 500.00')
    expect(screen.getByRole('table', { name: 'Risk decisions' })).toHaveTextContent('APPROVED')
    expect(screen.getByRole('table', { name: 'Paper fills' })).toHaveTextContent('BUY')
    expect(screen.getByRole('table', { name: 'Cash ledger' })).toHaveTextContent('USD 9,500.00')
    expect(screen.queryByRole('button', { name: /live/i })).not.toBeInTheDocument()
  })

  it('renders persisted weekly outcomes, calibration, attribution, and lessons', () => {
    render(<ApiWeeklyReviewPage asOf="2026-08-29T09:30:00Z" detail={{
      approvals: [],
      attributions: [{ category: 'TIMING_ERROR', controllable: true, id: 'a1', outcomeId: 'o1', rationale: 'Late entry.' }],
      calibration: [{ calibrationError: '0.2', confidence: '0.8', decisionId: 'd1', realizedReturn: '0.03', status: 'MATURED' }],
      lessons: [{ confidence: '0.7', id: 'l1', replayDelta: '0.1', statement: 'Wait for confirmation.', status: 'CANDIDATE' }],
      outcomes: [{ confidence: '0.8', decisionId: 'd1', id: 'o1', opinion: 'BULLISH', returns: { '1': '0.03' }, status: 'MATURED', symbol: 'NVDA' }],
      replays: [],
      review: { dataCutoff: '2026-08-21T20:00:00Z', id: 'r1', status: 'COMPLETED' },
    }} />)

    expect(screen.getByRole('heading', { name: 'Weekly Review' })).toBeInTheDocument()
    expect(screen.getByText('NVDA')).toBeInTheDocument()
    expect(screen.getByText('Late entry.')).toBeInTheDocument()
    expect(screen.getByText('Wait for confirmation.')).toBeInTheDocument()
    expect(screen.getAllByText('80.00%')).toHaveLength(2)
  })

  it('keeps API weekly benchmarks honest and replays ahead of candidate lessons', () => {
    render(<ApiWeeklyReviewPage asOf="2026-08-29T09:30:00Z" detail={{
      approvals: [],
      attributions: [],
      calibration: [],
      lessons: [{ confidence: '0.7', id: 'l1', replayDelta: '0.1', statement: 'Wait.', status: 'CANDIDATE' }],
      outcomes: [],
      replays: [{ dataCutoff: '2026-08-21T20:00:00Z', delta: '0.05', id: 'p1', lessonId: 'l1' }],
      review: { dataCutoff: '2026-08-21T20:00:00Z', id: 'r1', status: 'COMPLETED' },
    }} />)

    const outcomes = screen.getByRole('region', { name: 'Weekly outcome summary' })
    const replay = screen.getByRole('region', { name: 'Point-in-time replays' })
    const lessons = screen.getByRole('region', { name: 'Candidate lessons' })
    expect(outcomes).toHaveTextContent('Benchmark comparison unavailable')
    expect(replay).toHaveTextContent('Aug 21, 2026')
    expect(replay.compareDocumentPosition(lessons) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
