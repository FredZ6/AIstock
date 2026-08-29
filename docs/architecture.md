# Architecture

## Trust model

Deterministic code owns time eligibility, identifiers, scoring gates, alerts, risk, accounting,
policy authorization, and release gates. Agent graphs may gather and structure evidence within fixed
budgets, but they cannot cross the paper-only or human-approval boundaries.

## Component flow

```text
Read-only providers / frozen fixtures
        │
        ▼
MinIO RawDataObject ── durable dispatch outbox
        │
        ▼
PostgreSQL NormalizedRecord → versioned facts / DerivedMetric
        │
        ▼
EvidenceItem + EvidenceGap → Claim → InvestmentThesis
        │
        ▼
DecisionSnapshot → deterministic Alert / Portfolio Risk Gateway
        │                         │
        │                         └→ PaperOrder → PaperFill → CashLedger → NAV
        ▼
Weekly outcome attribution → Candidate Lesson → human approval → separate activation
```

Redis transports recoverable work and SSE events; PostgreSQL remains authoritative. A worker ACKs
only after durable persistence. MinIO content hashes and raw object keys preserve source lineage.

## Runtime surfaces

- FastAPI exposes the locked REST/SSE control plane and idempotent run admission.
- Celery/Beat schedules bounded research and ingestion work with durable database admission.
- Three research-only MCP servers expose approved SEC, market, and analyst tools.
- Next.js provides Today, Watchlist, Research, Run Trace, Portfolio, Alerts, Weekly Review, and
  Eval/Admin pages.
- OpenTelemetry correlation, structured logs, Prometheus metrics, and Grafana dashboards trace a
  run across HTTP, worker, graph, tool, persistence, and SSE boundaries.

## Data invariants

- Raw, normalized, evidence, thesis, decision, tool/event, paper fill, and ledger history is
  versioned or append-only as defined by v0.2.
- Thesis-to-evidence is normalized through `ThesisEvidenceLink`; no evidence-ID array is stored on a
  thesis.
- ResearchOpinion and PortfolioAction are different types and policies.
- Policy, prompt, model, and data cutoff are pinned on every decision run.
- Current TradingView widgets are visual reference only and are never decision-time evidence.

## Failure behavior

Missing or invalid provider data becomes typed Unavailable/Degraded/Abstain or No Action. Redis,
provider, explainer, and notification failures retain deterministic facts and recovery paths. API
mode never falls back to frozen Fixture records.
